"""데이터 관리: 탭 저장(임시) → 검사 → 적용(버전) → 고객 페이지에 주입.

- 탭 행은 studyroom_datasets 에 임시 저장되고, [적용] 시 studyroom_catalog_versions 에 버전으로 남는다.
- 고객 페이지는 활성 버전의 catalog·링크·사진 주소를 HTML 에 넣어 내려준다(버전별 캐시).
- 사진·제품가이드 PDF 파일은 DATA_DIR/files 아래(영속 볼륨)에 둔다.
"""
import hashlib
import json
import re
import secrets
import threading
from pathlib import Path

from . import catalog as C
from . import db

BASE = Path(__file__).resolve().parent
SEED = BASE / "seed"
FILES = db.DATA_DIR / "files"
IMG_DIR, GUIDE_DIR = FILES / "images", FILES / "guides"
TABS = {"products": C.PRODUCT_COLS, "sales": C.SALES_COLS, "features": C.FEATURE_COLS, "rules": C.RULE_COLS}
IMG_TYPES = {b"RIFF": "webp", b"\x89PNG": "png", b"\xff\xd8\xff": "jpg"}
CODE_RE = re.compile(r"^[A-Za-z0-9_-]{2,40}$")
ACTIVE = "active_catalog_version"

_lock = threading.Lock()
_page_cache: dict = {}
_seed_cache: dict = {}


def _seed():
    if not _seed_cache:
        _seed_cache.update(json.loads((SEED / "seed.json").read_text(encoding="utf-8")))
    return _seed_cache


def _setting(name, value=None, now=None):
    if value is None:
        rows = db.fetch_all("SELECT value FROM studyroom_settings WHERE name = ?", (name,))
        return rows[0]["value"] if rows else None
    db.execute("INSERT INTO studyroom_settings (name, value, updated_at) VALUES (?, ?, ?) "
               "ON CONFLICT (name) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
               (name, str(value), now))


# ── 탭 행 ───────────────────────────────────────────
def get_rows(tab):
    rows = db.fetch_all("SELECT rows FROM studyroom_datasets WHERE name = ?", (tab,))
    data = json.loads(rows[0]["rows"]) if rows else []
    return [C.upgrade_rule(r) for r in data] if tab == "rules" else data


def clean_rows(tab, rows, previous):
    """허용 컬럼만 남기고 문자열 정리. 제품특성의 숨은 값(_carry)은 같은 코드의 이전 행에서 이어받는다."""
    if not isinstance(rows, list) or len(rows) > 5000:
        raise ValueError("행 목록 형식이 올바르지 않아요.")
    carry = {r.get("code"): r.get("_carry") for r in previous if r.get("_carry")}
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        row = {k: ("" if r.get(k) is None else str(r.get(k)).strip())[:2000] for k in TABS[tab]}
        if tab == "rules":
            row = C.upgrade_rule(row)
        if not any(row.values()):
            continue
        if tab == "features":
            row["_carry"] = r.get("_carry") if isinstance(r.get("_carry"), dict) else carry.get(row["code"], {})
        out.append(row)
    return out


def save_rows(tab, rows, now):
    db.execute("INSERT INTO studyroom_datasets (name, rows, updated_at) VALUES (?, ?, ?) "
               "ON CONFLICT (name) DO UPDATE SET rows = excluded.rows, updated_at = excluded.updated_at",
               (tab, json.dumps(rows, ensure_ascii=False), now))


def stamps():
    """탭별 현재 내용 지문 — 관리자 화면이 불러온 뒤 다른 곳에서 바뀌었는지 확인용."""
    return {r["name"]: hashlib.sha1(r["rows"].encode("utf-8")).hexdigest()[:16]
            for r in db.fetch_all("SELECT name, rows FROM studyroom_datasets")}


def save_rows_checked(tab, rows, now, base):
    """화면이 불러온 내용(base)과 지금 DB 내용이 같을 때만 저장. 다르면 덮어쓰지 않는다."""
    with _lock:
        if base != stamps().get(tab, ""):
            raise LookupError(tab)
        save_rows(tab, rows, now)
        return stamps().get(tab, "")


def all_rows():
    return {t: get_rows(t) for t in TABS}


# ── 파일 ────────────────────────────────────────────
def image_map():
    """{코드: 공개 주소} — 파일 수정 시각을 붙여 캐시를 갱신한다."""
    if not IMG_DIR.exists():
        return {}
    return {p.stem: f"/files/img/{p.name}?v={int(p.stat().st_mtime)}" for p in IMG_DIR.iterdir() if p.is_file()}


def save_image(code, data: bytes):
    if not CODE_RE.match(code):
        raise ValueError(f"'{code}' 은(는) 코드 형식이 아니에요(파일 이름을 제품코드로 해 주세요).")
    if len(data) > 5 * 1024 * 1024:
        raise ValueError(f"{code}: 사진은 5MB 이하만 올릴 수 있어요.")
    ext = next((e for sig, e in IMG_TYPES.items() if data.startswith(sig)), None)
    if not ext or (ext == "webp" and data[8:12] != b"WEBP"):
        raise ValueError(f"{code}: webp·png·jpg 사진만 올릴 수 있어요.")
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    delete_image(code)
    (IMG_DIR / f"{code}.{ext}").write_bytes(data)


def delete_image(code):
    if IMG_DIR.exists() and CODE_RE.match(code):
        for p in IMG_DIR.glob(f"{code}.*"):
            p.unlink()


def guides():
    rows = db.fetch_all("SELECT id, name, size, created_at, sha256 FROM studyroom_files WHERE kind = 'guide' ORDER BY created_at DESC")
    for r in rows:  # 지문(sha256) 도입 전 파일은 처음 볼 때 계산해 둔다
        if not r["sha256"] and (GUIDE_DIR / f"{r['id']}.pdf").exists():
            r["sha256"] = hashlib.sha256((GUIDE_DIR / f"{r['id']}.pdf").read_bytes()).hexdigest()
            db.execute("UPDATE studyroom_files SET sha256 = ? WHERE id = ?", (r["sha256"], r["id"]))
    return rows


def save_guide(name, data: bytes, now):
    if not data.startswith(b"%PDF"):
        raise ValueError("PDF 파일만 올릴 수 있어요.")
    if len(data) > 30 * 1024 * 1024:
        raise ValueError("PDF는 30MB 이하만 올릴 수 있어요.")
    digest = hashlib.sha256(data).hexdigest()
    same = next((g for g in guides() if g["sha256"] == digest), None)
    if same:
        raise ValueError(f"이미 같은 파일이 있어요('{same['name']}')")
    gid = secrets.token_hex(6)
    GUIDE_DIR.mkdir(parents=True, exist_ok=True)
    (GUIDE_DIR / f"{gid}.pdf").write_bytes(data)
    safe = re.sub(r"[\\/:*?\"<>|\r\n]", "_", name)[:120] or "제품가이드.pdf"
    db.execute("INSERT INTO studyroom_files (id, kind, name, size, created_at, sha256) VALUES (?, 'guide', ?, ?, ?, ?)",
               (gid, safe, len(data), now, digest))
    return gid


def delete_guide(gid):
    if re.fullmatch(r"[0-9a-f]{12}", gid):
        (GUIDE_DIR / f"{gid}.pdf").unlink(missing_ok=True)
        db.execute("DELETE FROM studyroom_files WHERE id = ? AND kind = 'guide'", (gid,))


def guide_path(gid):
    if not re.fullmatch(r"[0-9a-f]{12}", gid):
        return None
    p = GUIDE_DIR / f"{gid}.pdf"
    return p if p.exists() else None


# ── 검사·적용 ───────────────────────────────────────
def check(rows=None):
    rows = rows or all_rows()
    errs, warns = C.validate(rows["products"], rows["sales"], rows["features"])
    if not errs:
        cat = C.compile_catalog(rows["products"], rows["sales"], rows["features"], _seed()["base"], set())
        e2, w2 = C.validate_rules(rows["rules"], cat["P"], cat["META"])
    else:
        e2, w2 = C.validate_rules(rows["rules"])
    return errs + e2, warns + w2


def diff(new, old):
    """적용 전 비교 요약(쉬운 우리말)."""
    out = []
    np_, op = {r["code"]: r for r in new["products"]}, {r["code"]: r for r in old.get("products", [])}
    added, removed = sorted(set(np_) - set(op)), sorted(set(op) - set(np_))
    price = [(c, op[c]["price"], np_[c]["price"]) for c in np_ if c in op and str(op[c]["price"]) != str(np_[c]["price"])]
    named = [c for c in np_ if c in op and op[c]["name"].strip() != np_[c]["name"].strip()]
    links = [c for c in np_ if (np_[c].get("naver_url") or "") != (op.get(c, {}).get("naver_url") or "")]
    if added: out.append(f"제품 추가 {len(added)}건: {', '.join(added[:10])}{' …' if len(added) > 10 else ''}")
    if removed: out.append(f"제품 삭제 {len(removed)}건(추천에서 빠져요): {', '.join(removed[:10])}{' …' if len(removed) > 10 else ''}")
    if price: out.append(f"판매가 변경 {len(price)}건: " + ", ".join(f"{c} {int(float(a)):,}→{int(float(b)):,}원" for c, a, b in price[:8]) + (" …" if len(price) > 8 else ""))
    if named: out.append(f"명칭 변경 {len(named)}건")
    if links: out.append(f"스마트스토어 링크 변경 {len(links)}건")
    for tab, label in (("sales", "판매량"), ("features", "제품특성"), ("rules", "고객 기반 데이터")):
        key = (lambda r: r["code"]) if tab != "rules" else (lambda r: "|".join(str(r.get(k, "")) for k in C.RULE_COLS[:5]))
        a = {key(r): {k: str(v) for k, v in r.items() if k != "_carry"} for r in new.get(tab, [])}
        b = {key(r): {k: str(v) for k, v in r.items() if k != "_carry"} for r in old.get(tab, [])}
        n = sum(1 for c in set(a) | set(b) if a.get(c) != b.get(c))
        if n: out.append(f"{label} 변경 {n}건")
    return out or ["바뀐 내용이 없어요."]


def publish(note, now):
    with _lock:
        rows = all_rows()
        errs, _ = check(rows)
        if errs:
            raise ValueError("오류를 먼저 고쳐 주세요: " + errs[0])
        imgs = image_map()
        cat = C.compile_catalog(rows["products"], rows["sales"], rows["features"], _seed()["base"], set(imgs))
        cat["RULES"] = C.compile_rules(rows["rules"], cat["P"], cat["META"])
        gmap = {g["id"]: f"/files/guide/{g['id']}.pdf" for g in guides()}
        for r in rows["features"]:
            if r.get("guide") in gmap and r["code"] in cat["META"]:
                cat["META"][r["code"]]["guideUrl"] = gmap[r["guide"]]
        prev = active_version()
        summary = diff(rows, prev["rows"] if prev else {})
        payload = {"catalog": cat, "links": C.links_of(rows["products"]),
                   "images": {c: u for c, u in imgs.items() if c in {r["code"] for r in rows["products"]}},
                   "rows": rows}
        vid = db.insert_returning_id(
            "INSERT INTO studyroom_catalog_versions (created_at, note, summary, payload) VALUES (?, ?, ?, ?)",
            (now, note[:200], json.dumps(summary, ensure_ascii=False), json.dumps(payload, ensure_ascii=False)))
        _setting(ACTIVE, vid, now)
        _page_cache.clear()
        return vid, summary


def versions(limit=30):
    rows = db.fetch_all("SELECT id, created_at, note, summary FROM studyroom_catalog_versions ORDER BY id DESC LIMIT ?", (limit,))
    for r in rows:
        r["summary"] = json.loads(r["summary"] or "[]")
    return rows


def active_version():
    vid = _setting(ACTIVE)
    if not vid:
        return None
    rows = db.fetch_all("SELECT id, created_at, note, payload FROM studyroom_catalog_versions WHERE id = ?", (int(vid),))
    if not rows:
        return None
    v = rows[0]
    p = json.loads(v["payload"])
    return {"id": v["id"], "created_at": v["created_at"], "note": v["note"], **p}


def rollback(vid, now):
    with _lock:
        rows = db.fetch_all("SELECT payload FROM studyroom_catalog_versions WHERE id = ?", (vid,))
        if not rows:
            raise ValueError("그 버전을 찾지 못했어요.")
        p = json.loads(rows[0]["payload"])
        for tab in TABS:
            save_rows(tab, p["rows"][tab], now)
        _setting(ACTIVE, vid, now)
        _page_cache.clear()


# ── 시작 시 초기 데이터 ─────────────────────────────
def ensure_seed(now):
    have = {r["name"] for r in db.fetch_all("SELECT name FROM studyroom_datasets")}
    if have and "rules" not in have:  # 규칙 탭 도입 이전 데이터 → 기존 엔진 규칙을 옮긴 기본 규칙 추가
        save_rows("rules", clean_rows("rules", _seed()["rules"], []), now)
        publish("고객 기반 데이터(기본 규칙) 추가", now)
    if not have:
        s = _seed()
        for tab in TABS:
            save_rows(tab, clean_rows(tab, s[tab], []), now)
    # 기본 사진은 이 서버의 보존 폴더에 한 번만 채운다(DB가 이미 채워져 있어도 — 사진 파일은 서버마다 따로 있음).
    # 표시 파일이 있으면 다시 채우지 않아, 관리자가 지운 사진이 재시작 때 되살아나지 않는다.
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    marker = IMG_DIR.parent / ".seed_images_done"
    if not marker.exists():
        for p in (SEED / "images").iterdir():
            if not any(IMG_DIR.glob(f"{p.stem}.*")):
                (IMG_DIR / p.name).write_bytes(p.read_bytes())
        marker.write_text(now, encoding="utf-8")
    if not active_version():
        publish("초기 데이터(학생방 플래너 v3)", now)


# ── 고객 페이지 ─────────────────────────────────────
def _js(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def render_page(template: Path):
    v = active_version()
    key = v["id"] if v else 0
    if key not in _page_cache:
        html = template.read_text(encoding="utf-8")
        if v:
            html = (html.replace("__DK_CATALOG__", _js(v["catalog"])).replace("__DK_LINKS__", _js(v["links"]))
                    .replace("__DK_IMAGES__", _js(v["images"])).replace("__DK_DATA_VERSION__", f"catalog-v{v['id']}"))
        _page_cache.clear()
        _page_cache[key] = html
    return _page_cache[key]
