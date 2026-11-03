"""DESKER 학생방 플래너 — 고객 설문 페이지 + 익명 응답 수집 + 관리자 페이지."""
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent


def _load_local_env():
    """로컬 실행용 .env 읽기(이미 있는 환경변수는 덮지 않음). 서버에서는 .env 가 이미지에 없다."""
    f = BASE.parent / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        os.environ.setdefault(k.strip(), v)


_load_local_env()

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.concurrency import run_in_threadpool  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response  # noqa: E402
from starlette.middleware.sessions import SessionMiddleware  # noqa: E402

from . import catalog as cat_rules  # noqa: E402
from . import data_store as ds  # noqa: E402
from . import db  # noqa: E402

KST = timezone(timedelta(hours=9))
PUBLIC = BASE / "public"
ADMIN = BASE / "admin"
LABELS = json.loads((BASE / "labels.json").read_text(encoding="utf-8"))

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "1") != "0"
MAX_BODY = 200_000

TRACK_TYPES = {"visit", "step"} | set(LABELS["events"])
ANSWER_KEYS = (set(LABELS["fields"]) | set(LABELS["numbers"]) | set(LABELS["texts"])
               | {"other", "allowLower", "unknownItems", "pricePolicy", "together"})
FREE_TEXT = {"other"} | set(LABELS["texts"])
SID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")
PHONE_RE = re.compile(r"0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

@asynccontextmanager
async def lifespan(_app):
    db.init()
    ds.ensure_seed(_now())
    print(f"[studyroom] storage = {db.backend_name()}", flush=True)
    if not ADMIN_PASSWORD:
        print("[studyroom] ADMIN_PASSWORD 미설정 — 관리자 로그인 불가", flush=True)
    yield


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.add_middleware(
    SessionMiddleware, secret_key=SECRET_KEY, session_cookie="dk_admin",
    max_age=12 * 3600, same_site="lax", https_only=COOKIE_SECURE,
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.path.startswith(("/api/admin", "/admin")):
        resp.headers["Cache-Control"] = "no-store"
    return resp


# ── 공통 ─────────────────────────────────────────────
_hits: dict = defaultdict(deque)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


def _rate_ok(key: str, limit: int, window: float) -> bool:
    now = time.monotonic()
    q = _hits[key]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


def _now() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def _device(ua: str) -> str:
    ua = ua or ""
    if re.search(r"iPad|Tablet", ua) or ("Android" in ua and "Mobile" not in ua):
        return "tablet"
    if re.search(r"Mobi|iPhone|Android", ua):
        return "mobile"
    return "pc"


async def _json_body(request: Request) -> dict:
    if not _rate_ok("pub:" + _client_ip(request), 240, 60):
        raise HTTPException(429, "too many requests")
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise HTTPException(413, "payload too large")
    try:
        data = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "invalid json")
    if not isinstance(data, dict) or not SID_RE.match(str(data.get("sid", ""))):
        raise HTTPException(400, "invalid sid")
    return data


def _short(v, n):
    return str(v)[:n] if v is not None else ""


def _int(v, lo=0, hi=10**9):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return None


def _clean_answers(a) -> dict:
    out = {}
    if not isinstance(a, dict):
        return out
    for k, v in a.items():
        if k not in ANSWER_KEYS:
            continue
        if k in FREE_TEXT:
            text = _short(v, 250 if k == "other" else 40)
            out[k] = EMAIL_RE.sub("[이메일 삭제]", PHONE_RE.sub("[연락처 삭제]", text))
        elif isinstance(v, list):
            out[k] = [_short(x, 30) for x in v[:20]]
        elif isinstance(v, bool) or v is None:
            out[k] = v
        elif isinstance(v, (int, float)):
            out[k] = v
        else:
            out[k] = _short(v, 30)
    return out


def _clean_results(rs) -> list:
    out = []
    for c in (rs if isinstance(rs, list) else [])[:3]:
        if not isinstance(c, dict):
            continue
        lines = []
        for ln in (c.get("lines") or [])[:30]:
            if isinstance(ln, dict):
                lines.append({
                    "code": _short(ln.get("code"), 30), "name": _short(ln.get("name"), 120),
                    "qty": _int(ln.get("qty"), 0, 99), "amount": _int(ln.get("amount")),
                    "color": _short(ln.get("color"), 10), "bundle": bool(ln.get("bundle")),
                })
        out.append({"label": _short(c.get("label"), 40), "amount": _int(c.get("amount")),
                    "partial": bool(c.get("partial")), "lines": lines})
    return out


def _ensure_session(sid: str, device: str, entry=None):
    now = _now()
    db.execute(
        "INSERT INTO studyroom_sessions (sid, created_at, updated_at, device, entry, max_step, submit_count) "
        "VALUES (?, ?, ?, ?, ?, 0, 0) ON CONFLICT (sid) DO UPDATE SET updated_at = excluded.updated_at",
        (sid, now, now, device, entry),
    )


# ── 고객용 ───────────────────────────────────────────
@app.get("/health")
def health():
    return {"ok": True}


@app.get("/")
def customer_page():
    return HTMLResponse(ds.render_page(PUBLIC / "index.html"), headers={"Cache-Control": "no-cache"})


IMG_NAME = re.compile(r"^[A-Za-z0-9_-]{2,40}\.(webp|png|jpg)$")


@app.get("/files/img/{name}")
def product_image(name: str):
    if not IMG_NAME.match(name) or not (ds.IMG_DIR / name).exists():
        raise HTTPException(404)
    mime = {"webp": "image/webp", "png": "image/png", "jpg": "image/jpeg"}[name.rsplit(".", 1)[1]]
    return FileResponse(ds.IMG_DIR / name, media_type=mime, headers={"Cache-Control": "public, max-age=300"})


@app.get("/files/guide/{gid}.pdf")
def product_guide(gid: str):
    path = ds.guide_path(gid)
    if not path:
        raise HTTPException(404)
    return FileResponse(path, media_type="application/pdf", headers={"Content-Disposition": "inline"})


@app.get("/collect.js")
def collect_js():
    return FileResponse(PUBLIC / "collect.js", media_type="text/javascript; charset=utf-8",
                        headers={"Cache-Control": "no-cache"})


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)


@app.get("/robots.txt")
def robots():
    return FileResponse(PUBLIC / "robots.txt", media_type="text/plain; charset=utf-8")


@app.post("/api/track")
async def track(request: Request):
    data = await _json_body(request)
    typ = str(data.get("type", ""))
    if typ not in TRACK_TYPES:
        raise HTTPException(400, "invalid type")
    sid = data["sid"]
    device = _device(request.headers.get("user-agent", ""))
    entry = data.get("entry") if data.get("entry") in LABELS["entries"] else None
    plan = _int(data.get("plan"), 0, 2)
    step = _int(data.get("step"), 0, 5)

    def work():
        _ensure_session(sid, device, entry)
        if typ == "step" and step is not None:
            db.execute("UPDATE studyroom_sessions SET max_step = CASE WHEN max_step < ? THEN ? ELSE max_step END "
                       "WHERE sid = ?", (step, step, sid))
        elif typ != "visit":
            db.execute("INSERT INTO studyroom_events (sid, at, type, plan) VALUES (?, ?, ?, ?)",
                       (sid, _now(), typ, plan))
            if typ in ("select-result", "shop", "consult") and plan is not None:
                db.execute("UPDATE studyroom_sessions SET selected = ? WHERE sid = ?", (plan, sid))

    await run_in_threadpool(work)
    return Response(status_code=204)


@app.post("/api/submit")
async def submit(request: Request):
    data = await _json_body(request)
    sid = data["sid"]
    kind = "update" if data.get("kind") == "update" else "complete"
    answers = json.dumps(_clean_answers(data.get("answers")), ensure_ascii=False)
    results = json.dumps(_clean_results(data.get("results")), ensure_ascii=False)
    selected = _int(data.get("selected"), 0, 2)
    version = _short(data.get("v"), 60)
    device = _device(request.headers.get("user-agent", ""))

    def work():
        _ensure_session(sid, device)
        now = _now()
        db.execute(
            "UPDATE studyroom_sessions SET answers = ?, results = ?, selected = ?, data_version = ?, "
            "max_step = 5, completed_at = COALESCE(completed_at, ?), updated_at = ?, "
            "submit_count = submit_count + ? WHERE sid = ?",
            (answers, results, selected, version, now, now, 1 if kind == "complete" else 0, sid),
        )
        if kind == "complete":
            db.execute("INSERT INTO studyroom_events (sid, at, type, plan) VALUES (?, ?, 'complete', ?)",
                       (sid, now, selected))

    await run_in_threadpool(work)
    return Response(status_code=204)


FEEDBACK_CATS = {"inconvenient": "불편한 점", "fix": "고쳐야 할 점", "feature": "추가됐으면 하는 기능", "etc": "기타"}
FEEDBACK_STATUS = {"new": "새 의견", "seen": "확인함", "done": "반영함"}
FEEDBACK_PLACES = {"step1": "1단계", "step2": "2단계", "step3": "3단계", "step4": "4단계", "step5": "5단계",
                   "results": "결과 화면", "home": "첫 화면"}
FEEDBACK_PER_SID = 10


@app.post("/api/feedback")
async def feedback(request: Request):
    data = await _json_body(request)
    sid = data["sid"]
    cat = str(data.get("category", ""))
    if cat not in FEEDBACK_CATS:
        raise HTTPException(400, "invalid category")
    msg = _short(data.get("message"), 1000).strip()
    if not msg:
        raise HTTPException(400, "empty message")
    msg = EMAIL_RE.sub("[이메일 삭제]", PHONE_RE.sub("[연락처 삭제]", msg))
    place = str(data.get("place", ""))
    place = place if place in FEEDBACK_PLACES else ""
    device = _device(request.headers.get("user-agent", ""))

    def work():
        n = db.fetch_all("SELECT COUNT(*) AS c FROM studyroom_feedback WHERE sid = ?", (sid,))[0]["c"]
        if int(n) >= FEEDBACK_PER_SID:
            return False
        _ensure_session(sid, device)
        db.execute("INSERT INTO studyroom_feedback (sid, created_at, category, message, place, device, status) "
                   "VALUES (?, ?, ?, ?, ?, ?, 'new')", (sid, _now(), cat, msg, place, device))
        return True

    if not await run_in_threadpool(work):
        raise HTTPException(429, "too many feedback")
    return Response(status_code=204)


# ── 관리자 ───────────────────────────────────────────
def _is_admin(request: Request) -> bool:
    return bool(request.session.get("admin"))


def _require_admin(request: Request):
    if not _is_admin(request):
        raise HTTPException(401, "login required")


@app.get("/admin")
def admin_page(request: Request):
    page = "index.html" if _is_admin(request) else "login.html"
    return FileResponse(ADMIN / page, media_type="text/html; charset=utf-8")


@app.post("/admin/login")
def admin_login(request: Request, password: str = Form("")):
    # IP 기준 + 전체 기준(X-Forwarded-For 위조로 IP 제한을 우회하는 경우 대비)
    if not _rate_ok("login:" + _client_ip(request), 10, 600) or not _rate_ok("login:*", 30, 600):
        return RedirectResponse("/admin?e=wait", status_code=303)
    if _check_password(password):
        request.session["admin"] = True
        return RedirectResponse("/admin", status_code=303)
    return RedirectResponse("/admin?e=1", status_code=303)


# 관리자 화면에서 바꾼 비밀번호는 해시로 저장되고, 저장된 값이 있으면 ADMIN_PASSWORD 보다 우선한다.
PW_SETTING = "admin_password_hash"


def _hash_password(pw: str) -> str:
    salt, iters = secrets.token_bytes(16), 200_000
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, iters)
    return f"pbkdf2_sha256${iters}${salt.hex()}${dk.hex()}"


def _check_password(pw: str) -> bool:
    rows = db.fetch_all("SELECT value FROM studyroom_settings WHERE name = ?", (PW_SETTING,))
    if rows:
        _, iters, salt, digest = rows[0]["value"].split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(dk.hex(), digest)
    return bool(ADMIN_PASSWORD) and hmac.compare_digest(pw.encode(), ADMIN_PASSWORD.encode())


@app.post("/api/admin/password")
async def admin_password(request: Request):
    _require_admin(request)
    if request.headers.get("x-requested-with") != "dk-admin":
        raise HTTPException(400)
    if not _rate_ok("pw:*", 10, 600):
        raise HTTPException(429, "잠시 후 다시 시도해 주세요.")
    try:
        data = json.loads(await request.body() or b"{}")
    except ValueError:
        raise HTTPException(400)
    current, new = str(data.get("current", "")), str(data.get("new", ""))
    if not 8 <= len(new) <= 128:
        raise HTTPException(400, "새 비밀번호는 8자 이상으로 정해 주세요.")
    if not await run_in_threadpool(_check_password, current):
        raise HTTPException(403, "현재 비밀번호가 맞지 않아요.")
    hashed = _hash_password(new)
    await run_in_threadpool(
        db.execute,
        "INSERT INTO studyroom_settings (name, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT (name) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (PW_SETTING, hashed, _now()))
    return {"ok": True}


@app.post("/admin/logout")
def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin", status_code=303)


ADMIN_ASSETS = {"admin.css": "text/css", "admin.js": "text/javascript", "admin_data.js": "text/javascript",
                "admin_feedback.js": "text/javascript", "qrcode.js": "text/javascript"}


@app.get("/admin/assets/{name}")
def admin_asset(name: str):
    if name == "engine.js":
        return admin_engine_js()
    if name not in ADMIN_ASSETS:
        raise HTTPException(404)
    return FileResponse(ADMIN / name, media_type=ADMIN_ASSETS[name] + "; charset=utf-8")


def _range(frm: str | None, to: str | None):
    try:
        d1 = date.fromisoformat(frm) if frm else date(2000, 1, 1)
        d2 = date.fromisoformat(to) if to else date(2100, 1, 1)
    except ValueError:
        raise HTTPException(400, "invalid date")
    return d1.isoformat() + "T00:00:00", (d2 + timedelta(days=1)).isoformat() + "T00:00:00"


def _load_sessions(frm, to):
    lo, hi = _range(frm, to)
    rows = db.fetch_all(
        "SELECT sid, created_at, completed_at, device, entry, max_step, submit_count, data_version, "
        "answers, results, selected FROM studyroom_sessions WHERE created_at >= ? AND created_at < ? "
        "ORDER BY created_at DESC", (lo, hi))
    ev = db.fetch_all(
        "SELECT e.sid, e.type, COUNT(*) AS c FROM studyroom_events e JOIN studyroom_sessions s ON s.sid = e.sid "
        "WHERE s.created_at >= ? AND s.created_at < ? GROUP BY e.sid, e.type", (lo, hi))
    counts = defaultdict(dict)
    for e in ev:
        counts[e["sid"]][e["type"]] = int(e["c"])
    for r in rows:
        r["answers"] = json.loads(r["answers"]) if r["answers"] else None
        r["results"] = json.loads(r["results"]) if r["results"] else []
        r["events"] = counts.get(r["sid"], {})
    return rows


@app.get("/api/admin/meta")
def admin_meta(request: Request):
    _require_admin(request)
    return {"labels": LABELS, "storage": "PostgreSQL" if db.IS_PG else "SQLite"}


@app.get("/api/admin/sessions")
def admin_sessions(request: Request, frm: str | None = None, to: str | None = None):
    _require_admin(request)
    return JSONResponse(_load_sessions(frm, to))


@app.delete("/api/admin/sessions/{sid}")
def admin_delete(request: Request, sid: str):
    _require_admin(request)
    if request.headers.get("x-requested-with") != "dk-admin" or not SID_RE.match(sid):
        raise HTTPException(400)
    db.execute("DELETE FROM studyroom_events WHERE sid = ?", (sid,))
    db.execute("DELETE FROM studyroom_sessions WHERE sid = ?", (sid,))
    return Response(status_code=204)


def _label(field: str, value):
    f = LABELS["fields"].get(field)
    if not f:
        return value
    opts = LABELS["fields"][f["ref"]]["options"] if "ref" in f else f["options"]
    if isinstance(value, list):
        return ", ".join(opts.get(str(v), str(v)) for v in value)
    if value in (None, ""):
        return ""
    return opts.get(str(value), str(value))


def _kst(ts):
    return ts[:16].replace("T", " ") if ts else ""


@app.get("/api/admin/export.xlsx")
def admin_export(request: Request, frm: str | None = None, to: str | None = None):
    _require_admin(request)
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    rows = _load_sessions(frm, to)
    wb = Workbook()
    ws = wb.active
    ws.title = "응답"
    fields = list(LABELS["fields"])
    nums = list(LABELS["numbers"])
    texts = list(LABELS["texts"])
    head = (["응답ID", "접속시각", "완료시각", "기기", "진입", "도달단계", "완료"] +
            [LABELS["fields"][f]["name"] for f in fields] + [LABELS["numbers"][n] for n in nums] +
            [LABELS["texts"][t] for t in texts] +
            ["추가 요청", "선택 추천안", "선택안 금액", "1안", "1안 금액", "2안", "2안 금액", "3안", "3안 금액"] +
            [LABELS["events"][k] for k in LABELS["events"]])
    ws.append(head)
    for r in rows:
        a = r["answers"] or {}
        res = r["results"] or []
        sel = r["selected"] if r["selected"] is not None and r["selected"] < len(res) else (0 if res else None)
        plans = []
        for i in range(3):
            plans += [res[i]["label"], res[i]["amount"]] if i < len(res) else ["", ""]
        ws.append(
            [r["sid"][:8], _kst(r["created_at"]), _kst(r["completed_at"]), LABELS["devices"].get(r["device"], r["device"]),
             LABELS["entries"].get(r["entry"] or "", r["entry"] or ""), r["max_step"], "Y" if r["completed_at"] else ""] +
            [_label(f, a.get(f)) for f in fields] + [a.get(n) for n in nums] + [a.get(t, "") for t in texts] +
            [a.get("other", ""), res[sel]["label"] if sel is not None else "", res[sel]["amount"] if sel is not None else ""] +
            plans + [r["events"].get(k, 0) for k in LABELS["events"]])

    ws2 = wb.create_sheet("추천 구성")
    ws2.append(["응답ID", "완료시각", "추천안", "선택여부", "구성금액", "제품코드", "제품명", "색상", "수량", "금액", "묶음"])
    for r in rows:
        for i, p in enumerate(r["results"] or []):
            for ln in p["lines"]:
                ws2.append([r["sid"][:8], _kst(r["completed_at"]), p["label"], "Y" if r["selected"] == i else "",
                            p["amount"], ln["code"], ln["name"], ln["color"], ln["qty"], ln["amount"],
                            "Y" if ln["bundle"] else ""])
    for sheet in (ws, ws2):
        for c in sheet[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="282828")
        sheet.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    name = f"studyroom_responses_{datetime.now(KST):%Y%m%d_%H%M}.xlsx"
    return Response(buf.getvalue(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ── 데이터 관리(제품·판매량·제품특성) ───────────────────────
HEADERS = {
    "products": {"unit": "판매단위", "cat": "구분", "code": "코드", "name": "공식명칭",
                 "naver_url": "스마트스토어 링크", "price": "판매가"},
    "sales": {"code": "코드", "group": "구분", "name": "명칭", "monthly": "월평균 판매량"},
    "features": {"code": "코드", "tier": "단수", "width": "폭(mm)", "depth": "깊이(mm)", "wall": "벽고정",
                 "min_ceiling": "최소 천장(cm)", "motion": "모션", "multi": "멀티", "light": "조명",
                 "colors": "판매 색상", "features": "특징", "checks": "구매 전 확인", "guide": "제품가이드"},
    "rules": {"field": "질문", "values": "답", "cats": "대상 구분", "target_type": "대상 조건", "target": "대상 값",
              "level": "등급", "memo": "근거 메모", "on": "사용"},
}


def _require_mutation(request: Request):
    _require_admin(request)
    if request.headers.get("x-requested-with") != "dk-admin":
        raise HTTPException(400)


def _tab(tab: str):
    if tab not in ds.TABS:
        raise HTTPException(404)
    return tab


@app.get("/api/admin/data")
def admin_data(request: Request):
    _require_admin(request)
    rows = ds.all_rows()
    errs, warns = ds.check(rows)
    act = ds.active_version()
    return {"rows": rows, "stamps": ds.stamps(), "headers": HEADERS, "images": ds.image_map(), "guides": ds.guides(),
            "errors": errs, "warnings": warns, "versions": ds.versions(),
            "active": {"id": act["id"], "created_at": act["created_at"], "note": act["note"]} if act else None,
            "options": {"unit": list(cat_rules.UNITS), "cat": list(cat_rules.CATS) + [cat_rules.BUNDLE_LABEL],
                        "group": list(cat_rules.SALES_GROUPS), "wall": list(cat_rules.WALLS),
                        "level": list(cat_rules.LEVELS), "target_type": cat_rules.TARGET_TYPES,
                        "features": list(cat_rules.FEATURE_TARGETS), "questions": cat_rules.RULE_QUESTIONS,
                        "catsOnly": list(cat_rules.CATS)}}


@app.put("/api/admin/data/{tab}")
async def admin_data_save(request: Request, tab: str):
    _require_mutation(request)
    _tab(tab)
    raw = await request.body()
    if len(raw) > 5_000_000:
        raise HTTPException(413)
    try:
        body = json.loads(raw)
        rows = ds.clean_rows(tab, body.get("rows"), ds.get_rows(tab))
    except (ValueError, AttributeError) as e:
        raise HTTPException(400, str(e) or "형식 오류")

    def work():
        # 화면을 연 뒤 다른 관리자 화면·일괄 입력으로 바뀐 내용을 옛 화면이 덮어쓰지 않게 한다
        stamp = ds.save_rows_checked(tab, rows, _now(), str(body.get("base") or ""))
        return (stamp, *ds.check())
    try:
        stamp, errs, warns = await run_in_threadpool(work)
    except LookupError:
        label = {"products": "제품", "sales": "책상세트 판매량", "features": "제품특성", "rules": "고객 기반 데이터"}[tab]
        raise HTTPException(409, f"화면을 연 뒤 다른 곳에서 '{label}' 데이터가 바뀌었어요. 덮어쓰지 않도록 저장을 멈췄어요. "
                                 "새로고침(F5)한 뒤 다시 고쳐서 저장해 주세요.")
    return {"saved": len(rows), "stamp": stamp, "errors": errs, "warnings": warns}


_engine_js: dict = {}


def admin_engine_js():
    """시험 설문 비교용: 고객 페이지에 들어간 추천 엔진 스크립트를 그대로 내려준다."""
    if "src" not in _engine_js:
        html = (PUBLIC / "index.html").read_text(encoding="utf-8")
        block = next((b for b in re.findall(r"<script>(.*?)</script>", html, re.S) if "function createEngine" in b), "")
        _engine_js["src"] = block
    return Response(_engine_js["src"], media_type="text/javascript; charset=utf-8")


@app.get("/api/admin/data/catalogs")
def admin_data_catalogs(request: Request):
    """시험 설문 비교: 지금 적용 중인 데이터 vs 저장된(적용 전) 데이터."""
    _require_admin(request)
    rows = ds.all_rows()
    errs, _ = ds.check(rows)
    if errs:
        raise HTTPException(400, "저장된 데이터에 오류가 있어 비교할 수 없어요: " + errs[0])
    draft = cat_rules.compile_catalog(rows["products"], rows["sales"], rows["features"], ds._seed()["base"], set())
    draft["RULES"] = cat_rules.compile_rules(rows["rules"], draft["P"], draft["META"])
    act = ds.active_version()
    keys = {f: {v: k for k, v in cat_rules._opts(f).items()} for f in ("age", "budget", "needs", "use", "motion", "storageType")}
    return {"active": act["catalog"], "activeId": act["id"], "draft": draft, "keys": keys}


@app.post("/api/admin/data/preview")
def admin_data_preview(request: Request):
    _require_mutation(request)
    rows = ds.all_rows()
    errs, warns = ds.check(rows)
    act = ds.active_version()
    return {"errors": errs, "warnings": warns, "diff": ds.diff(rows, act["rows"] if act else {})}


@app.post("/api/admin/data/publish")
async def admin_data_publish(request: Request):
    _require_mutation(request)
    try:
        note = str(json.loads(await request.body() or b"{}").get("note", ""))
    except ValueError:
        note = ""
    try:
        vid, summary = await run_in_threadpool(ds.publish, note or "관리자 적용", _now())
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"version": vid, "summary": summary}


@app.post("/api/admin/data/rollback/{vid}")
def admin_data_rollback(request: Request, vid: int):
    _require_mutation(request)
    try:
        ds.rollback(vid, _now())
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"ok": True}


@app.get("/api/admin/data/export/{tab}.xlsx")
def admin_data_export(request: Request, tab: str):
    _require_admin(request)
    _tab(tab)
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = {"products": "제품", "sales": "판매량", "features": "제품특성", "rules": "고객기반데이터"}[tab]
    cols = ds.TABS[tab]
    ws.append([HEADERS[tab][c] for c in cols])
    for r in ds.get_rows(tab):
        ws.append([r.get(c, "") for c in cols])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="282828")
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    name = f"studyroom_{tab}_{datetime.now(KST):%Y%m%d_%H%M}.xlsx"
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.post("/api/admin/data/import/{tab}")
async def admin_data_import(request: Request, tab: str, file: UploadFile = File(...)):
    """엑셀 첫 행의 컬럼명으로 읽어 행 목록을 돌려준다(저장은 화면에서 [저장]을 눌러야 함)."""
    _require_mutation(request)
    _tab(tab)
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413)
    from openpyxl import load_workbook
    try:
        ws = load_workbook(io.BytesIO(data), read_only=True, data_only=True).worksheets[0]
        it = ws.iter_rows(values_only=True)
        head = [str(h or "").strip() for h in next(it)]
    except Exception:
        raise HTTPException(400, "엑셀(xlsx) 파일을 읽지 못했어요.")
    by_label = {v: k for k, v in HEADERS[tab].items()}
    idx = {by_label[h]: i for i, h in enumerate(head) if h in by_label}
    if "code" not in idx:
        raise HTTPException(400, "첫 행에 '코드' 열이 있어야 해요. (엑셀 내려받기 양식을 참고해 주세요)")
    rows = []
    for r in it:
        row = {k: ("" if r[i] is None else str(int(r[i]) if isinstance(r[i], float) and r[i].is_integer() else r[i]).strip())
               for k, i in idx.items() if i < len(r)}
        if any(row.values()):
            rows.append(row)
    return {"rows": rows, "matched": [HEADERS[tab][k] for k in idx], "count": len(rows)}


@app.post("/api/admin/files/images")
async def admin_upload_images(request: Request, files: list[UploadFile] = File(...), code: str = Form("")):
    """사진 업로드. code 가 없으면 파일 이름(확장자 제외)을 제품코드로 쓴다."""
    _require_mutation(request)
    done, failed = [], []
    for f in files[:300]:
        c = (code or Path(f.filename or "").stem).strip()
        try:
            data = await f.read()
            await run_in_threadpool(ds.save_image, c, data)
            done.append(c)
        except ValueError as e:
            failed.append(str(e))
    return {"saved": done, "failed": failed, "images": ds.image_map()}


@app.delete("/api/admin/files/images/{code}")
def admin_delete_image(request: Request, code: str):
    _require_mutation(request)
    ds.delete_image(code)
    return Response(status_code=204)


@app.post("/api/admin/files/guides")
async def admin_upload_guides(request: Request, files: list[UploadFile] = File(...)):
    _require_mutation(request)
    done, failed = [], []
    for f in files[:50]:
        try:
            data = await f.read()
            done.append(await run_in_threadpool(ds.save_guide, f.filename or "제품가이드.pdf", data, _now()))
        except ValueError as e:
            failed.append(f"{f.filename}: {e}")
    return {"saved": done, "failed": failed, "guides": ds.guides()}


@app.delete("/api/admin/files/guides/{gid}")
def admin_delete_guide(request: Request, gid: str):
    _require_mutation(request)
    ds.delete_guide(gid)
    return Response(status_code=204)


# ── 고객 의견 ────────────────────────────────────────
def _load_feedback(frm, to):
    lo, hi = _range(frm, to)
    rows = db.fetch_all(
        "SELECT f.id, f.sid, f.created_at, f.category, f.message, f.place, f.device, f.status, f.updated_at, "
        "s.completed_at FROM studyroom_feedback f LEFT JOIN studyroom_sessions s ON s.sid = f.sid "
        "WHERE f.created_at >= ? AND f.created_at < ? ORDER BY f.created_at DESC", (lo, hi))
    for r in rows:
        r["id"] = int(r["id"])
    return rows


@app.get("/api/admin/feedback")
def admin_feedback(request: Request, frm: str | None = None, to: str | None = None):
    _require_admin(request)
    return {"rows": _load_feedback(frm, to),
            "labels": {"categories": FEEDBACK_CATS, "status": FEEDBACK_STATUS, "places": FEEDBACK_PLACES}}


@app.post("/api/admin/feedback/{fid}/status")
async def admin_feedback_status(request: Request, fid: int):
    _require_mutation(request)
    data = await request.json()
    st = str((data or {}).get("status", ""))
    if st not in FEEDBACK_STATUS:
        raise HTTPException(400, "invalid status")
    await run_in_threadpool(db.execute, "UPDATE studyroom_feedback SET status = ?, updated_at = ? WHERE id = ?",
                            (st, _now(), fid))
    return Response(status_code=204)


@app.delete("/api/admin/feedback/{fid}")
def admin_feedback_delete(request: Request, fid: int):
    _require_mutation(request)
    db.execute("DELETE FROM studyroom_feedback WHERE id = ?", (fid,))
    return Response(status_code=204)


@app.get("/api/admin/feedback.xlsx")
def admin_feedback_export(request: Request, frm: str | None = None, to: str | None = None):
    _require_admin(request)
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "고객 의견"
    ws.append(["받은 시각", "의견 종류", "내용", "보낸 화면", "기기", "설문 완료", "처리 상태", "응답ID"])
    for r in _load_feedback(frm, to):
        msg = "'" + r["message"] if r["message"][:1] in ("=", "+", "-", "@") else r["message"]  # 엑셀 수식 실행 방지
        ws.append([_kst(r["created_at"]), FEEDBACK_CATS.get(r["category"], r["category"]), msg,
                   FEEDBACK_PLACES.get(r["place"] or "", r["place"] or ""), LABELS["devices"].get(r["device"], r["device"]),
                   "Y" if r["completed_at"] else "", FEEDBACK_STATUS.get(r["status"], r["status"]), r["sid"][:8]])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="282828")
    ws.freeze_panes = "A2"
    ws.column_dimensions["C"].width = 70
    for row in ws.iter_rows(min_row=2, min_col=3, max_col=3):
        row[0].alignment = Alignment(wrap_text=True, vertical="top")
    buf = io.BytesIO()
    wb.save(buf)
    name = f"studyroom_feedback_{datetime.now(KST):%Y%m%d_%H%M}.xlsx"
    return Response(buf.getvalue(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
