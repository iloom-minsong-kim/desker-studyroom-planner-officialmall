"""데이터 관리 탭(제품·판매량·제품특성) 행 → 추천 엔진용 catalog 변환과 검사.

엔진(source/customer_v3.html 의 engine.js)이 쓰는 형태:
  P[code]       = [code, 명칭, 판매가, 분류(cat), 단수, 표시명]
  META[code]    = {family, cat, tier, width, depth, wall, minCeiling, motion, multi, light, features, checks, variants, ...}
  BUNDLES[책상][의자] = {code, name, variants}   # 책상+의자 세트 판매코드
  SALES_PRIORITY[code] = {group, rank, groupSize, priority, measured}
"""
import math
import re

# 구분(화면 표기) ↔ 엔진 분류
CATS = {
    "책상": "desk0", "책상세트": "desk", "모션데스크": "mdesk0", "모션데스크 세트": "mdesk",
    "의자": "chair", "침대": "bed", "옷장": "ward", "책장": "shelf", "낮은 수납장": "low",
    "거울 수납장": "mirror", "서랍": "drawer", "정리용품": "organizer", "모니터받침대": "monitorstand",
    "모니터암": "monitorarm", "조명": "light",
}
BUNDLE_LABEL = "책상+의자 세트"
CAT_LABEL = {v: k for k, v in CATS.items()}
DESK_CATS = {"desk0", "desk", "mdesk0", "mdesk"}
UNITS = ("단품", "세트")
WALLS = {"없음": "none", "조건부": "conditional", "필수": "required"}
WALL_LABEL = {v: k for k, v in WALLS.items()}
SALES_GROUPS = {"일반": "regular", "모션": "motion"}
NAVER_RE = re.compile(r"^https://(smartstore|brand)\.naver\.com/[^/\s]+/products/\d+")

PRODUCT_COLS = ["unit", "cat", "code", "name", "naver_url", "price"]
SALES_COLS = ["code", "group", "name", "monthly"]
FEATURE_COLS = ["code", "tier", "width", "depth", "wall", "min_ceiling", "motion", "multi", "light",
                "colors", "features", "checks", "guide"]


def _num(v):
    if v in (None, ""):
        return None
    try:
        f = float(str(v).replace(",", "").strip())
    except ValueError:
        return "ERR"
    return int(f) if f.is_integer() else f


def _yes(v):
    return str(v).strip().upper() in ("Y", "YES", "TRUE", "1", "O", "예")


def _norm(s):
    # 세트 명칭에는 책상 명칭의 '(벽고정)' 표기가 빠져 있는 경우가 있어 비교에서 제외
    return re.sub(r"[\s,]", "", str(s or "").replace("(벽고정)", ""))


def _display(name):
    return re.sub(r"^\[[A-Z]+\]\s*", "", name)


def parse_bundle(name, products):
    """'W1200 5단 책상세트 콘센트형+링고(발받침)' → (책상코드, 의자코드) 또는 (None, None)."""
    if "+" not in name:
        return None, None
    left, right = name.rsplit("+", 1)
    left, right = left.strip(), right.strip()
    word = re.split(r"[\s(]", right, 1)[0]
    chair = next((r["code"] for r in products if r["cat"] == "의자" and word and _norm(r["name"]).startswith(_norm(word))), None)
    target = _norm(left)
    desk = next((r["code"] for r in products if CATS.get(r["cat"]) in DESK_CATS and _norm(r["name"]) == target), None)
    return desk, chair


def validate(products, sales, features):
    """(errors, warnings) — 오류가 있으면 적용 불가."""
    errs, warns = [], []
    seen = set()
    for i, r in enumerate(products, 1):
        tag = f"제품 {i}행({r.get('code') or '코드 없음'})"
        if not r.get("code"):
            errs.append(f"{tag}: 코드가 비어 있어요.")
            continue
        if r["code"] in seen:
            errs.append(f"{tag}: 코드가 중복돼요.")
        seen.add(r["code"])
        if r.get("unit") not in UNITS:
            errs.append(f"{tag}: 판매단위는 단품·세트 중 하나여야 해요.")
        if r.get("cat") not in CATS and r.get("cat") != BUNDLE_LABEL:
            errs.append(f"{tag}: 구분 '{r.get('cat')}' 을(를) 알 수 없어요.")
        if not r.get("name"):
            errs.append(f"{tag}: 공식명칭이 비어 있어요.")
        p = _num(r.get("price"))
        if p in (None, "ERR") or p <= 0:
            errs.append(f"{tag}: 판매가는 0보다 큰 숫자여야 해요.")
        if r.get("naver_url") and not NAVER_RE.match(r["naver_url"].strip()):
            errs.append(f"{tag}: 스마트스토어 링크는 smartstore/brand.naver.com 상품 상세 주소여야 해요.")
    codes = {r.get("code"): r for r in products if r.get("code")}
    for r in products:
        if r.get("cat") == BUNDLE_LABEL and r.get("code"):
            d, c = parse_bundle(r.get("name", ""), products)
            if not (d and c):
                warns.append(f"세트 {r['code']}: 명칭에서 책상·의자를 찾지 못해 세트 가격으로 계산하지 않아요(책상·의자 개별 가격 사용).")
    sseen = set()
    for i, r in enumerate(sales, 1):
        tag = f"판매량 {i}행({r.get('code') or '코드 없음'})"
        if r.get("code") not in codes:
            warns.append(f"{tag}: 제품 탭에 없는 코드라 쓰이지 않아요.")
        elif CATS.get(codes[r["code"]]["cat"]) not in DESK_CATS:
            warns.append(f"{tag}: 책상류가 아니라 판매량 가산에 쓰이지 않아요.")
        if r.get("code") in sseen:
            errs.append(f"{tag}: 코드가 중복돼요.")
        sseen.add(r.get("code"))
        if r.get("group") not in SALES_GROUPS:
            errs.append(f"{tag}: 구분은 일반·모션 중 하나여야 해요.")
        m = _num(r.get("monthly"))
        if m in (None, "ERR") or m < 0:
            errs.append(f"{tag}: 월평균 판매량은 0 이상 숫자여야 해요.")
    fseen = set()
    for i, r in enumerate(features, 1):
        tag = f"제품특성 {i}행({r.get('code') or '코드 없음'})"
        if r.get("code") not in codes:
            warns.append(f"{tag}: 제품 탭에 없는 코드라 쓰이지 않아요.")
        if r.get("code") in fseen:
            errs.append(f"{tag}: 코드가 중복돼요.")
        fseen.add(r.get("code"))
        for k, label in (("tier", "단수"), ("width", "폭"), ("depth", "깊이"), ("min_ceiling", "최소 천장")):
            if _num(r.get(k)) == "ERR":
                errs.append(f"{tag}: {label}는 숫자여야 해요.")
        if r.get("wall") and r["wall"] not in WALLS:
            errs.append(f"{tag}: 벽고정은 없음·조건부·필수 중 하나여야 해요.")
    missing = [c for c, r in codes.items() if r.get("cat") != BUNDLE_LABEL and c not in fseen]
    if missing:
        warns.append(f"제품특성이 없는 제품 {len(missing)}개는 명칭으로 단수·폭·벽고정을 추정해요: {', '.join(missing[:8])}{' …' if len(missing) > 8 else ''}")
    return errs, warns


def compile_catalog(products, sales, features, base, has_image):
    """행 데이터 → 엔진 catalog. base 는 시드 catalog(BR·REFERENCE_SIGNATURES·meta 재사용)."""
    feat = {r["code"]: r for r in features}
    P, META, BUNDLES = {}, {}, {}
    for r in products:
        if r["cat"] == BUNDLE_LABEL:
            continue
        code, name, price, cat = r["code"], r["name"].strip(), int(_num(r["price"])), CATS[r["cat"]]
        f = feat.get(code)
        carry = (f or {}).get("_carry") or {}
        if f:
            tier, width, depth = _num(f.get("tier")), _num(f.get("width")), _num(f.get("depth"))
            wall = WALLS.get(f.get("wall") or "없음", "none")
            min_ceiling = _num(f.get("min_ceiling"))
            motion, multi, light = _yes(f.get("motion")), _yes(f.get("multi")), _yes(f.get("light"))
            colors = [c.strip() for c in re.split(r"[,\s/]+", f.get("colors") or "") if c.strip()]
            feats = [x.strip() for x in re.split(r"[|\n]", f.get("features") or "") if x.strip()]
            checks = [x.strip() for x in re.split(r"[|\n]", f.get("checks") or "") if x.strip()]
        else:  # 제품특성 미입력 → 명칭으로 보수적 추정
            m = re.search(r"(\d)단", name)
            tier = int(m.group(1)) if m else None
            m = re.search(r"W(\d{3,4})", name)
            width, depth = (int(m.group(1)) if m else None), None
            wall = "required" if "벽고정" in name else "none"
            min_ceiling = None
            motion, multi, light = cat in ("mdesk", "mdesk0"), "멀티" in name, "조명" in name
            colors, feats = [], [name]
            checks = ["제품 규격·설치 조건은 매장 또는 상세페이지에서 확인해 주세요."]
        variants = [{"color": c, "price": price, "row": None} for c in colors] or [{"color": "기본", "price": price, "row": None}]
        P[code] = [code, name, price, cat, tier, _display(name)]
        META[code] = {
            "family": carry.get("family") or cat, "cat": cat, "tier": tier, "width": width, "depth": depth,
            "wall": wall, "minCeiling": min_ceiling, "ceilingUncertain": bool(carry.get("ceilingUncertain")),
            "motion": motion, "multi": multi, "light": light, "features": feats or [name], "checks": checks,
            "guideIds": carry.get("guideIds") or [], "sources": carry.get("sources") or [],
            "variants": variants, "defaultColor": colors[0] if colors else None,
            "priceKind": carry.get("priceKind") or "workbook", "priceSource": "데이터 관리", "row": None,
            "hasImage": code in has_image, "selectable": True,
        }
    for r in products:
        if r["cat"] != BUNDLE_LABEL:
            continue
        d, c = parse_bundle(r["name"], products)
        if not (d in P and c in P):
            continue
        price = int(_num(r["price"]))
        colors = [v["color"] for v in META[d]["variants"]]
        BUNDLES.setdefault(d, {})[c] = {"code": r["code"], "name": r["name"].strip(),
                                         "variants": [{"color": col, "price": price, "row": None} for col in colors],
                                         "source": "데이터 관리"}
    SALES = {}
    for key, grp in SALES_GROUPS.items():
        rows = [r for r in sales if r.get("group") == key and r.get("code") in P and META[r["code"]]["cat"] in DESK_CATS]
        rows.sort(key=lambda r: -float(_num(r["monthly"]) or 0))
        top = float(_num(rows[0]["monthly"]) or 0) if rows else 0
        for rank, r in enumerate(rows, 1):
            v = float(_num(r["monthly"]) or 0)
            SALES[r["code"]] = {"group": grp, "rank": rank, "groupSize": len(rows),
                                "priority": round(math.log1p(v) / math.log1p(top), 6) if top else 0, "measured": True}
    meta = dict(base.get("meta") or {})
    meta.update(productCount=len(P), bundleCount=sum(len(v) for v in BUNDLES.values()),
                photoCount=sum(1 for c in P if c in has_image), source="데이터 관리")
    return {"P": P, "META": META, "BR": base["BR"], "BUNDLES": BUNDLES,
            "REFERENCE_SIGNATURES": base.get("REFERENCE_SIGNATURES") or [], "meta": meta, "SALES_PRIORITY": SALES}


def links_of(products):
    return {r["code"]: r["naver_url"].strip() for r in products if (r.get("naver_url") or "").strip()}


# ── 고객 기반 데이터(선호 규칙) ─────────────────────────
# 한 행 = 조건(설문 질문·답) → 대상(구분 한정 + 코드/특성/명칭 포함) → 등급
import json as _json
from pathlib import Path as _Path

LABELS = _json.loads((_Path(__file__).resolve().parent / "labels.json").read_text(encoding="utf-8"))
RULE_FIELDS = ["age", "reason", "needs", "use", "useSel", "motion", "storageType", "monitor", "room", "budget", "channel", "count"]
LEVELS = {"우선 추천": 30, "추천": 15, "비추천": -15, "제외": None}
TARGET_TYPES = ["전체", "코드", "특성", "명칭 포함"]
FEATURE_TARGETS = {"모션": lambda m: m["motion"], "멀티": lambda m: m["multi"], "조명": lambda m: m["light"],
                   **{f"{n}단": (lambda n: lambda m: m["tier"] == n)(n) for n in range(1, 7)}}
RULE_COLS = ["field", "values", "cats", "target_type", "target", "level", "memo", "on"]


def _opts(field):
    f = LABELS["fields"][field]
    return LABELS["fields"][f["ref"]]["options"] if "ref" in f else f["options"]


QUESTION_OF = {LABELS["fields"][f]["name"]: f for f in RULE_FIELDS}
RULE_QUESTIONS = {LABELS["fields"][f]["name"]: list(_opts(f).values()) for f in RULE_FIELDS}
# 질문·답 이름을 바꾸기 전에 저장된 규칙('아이 나이' 등)도 그대로 읽히도록 옛 이름을 새 이름으로 바꿔 준다
_LEGACY_QUESTION = {"아이 나이": "자녀 나이", "아이 수": "자녀 수"}
_LEGACY_VALUE = {"아이가 자라서": "자녀가 자라서", "아이 취향": "자녀 취향"}


def upgrade_rule(r):
    r = dict(r)
    r["field"] = _LEGACY_QUESTION.get(r.get("field"), r.get("field"))
    vals = str(r.get("values") or "")
    for old, new in _LEGACY_VALUE.items():
        vals = vals.replace(old, new)
    r["values"] = vals
    return r


def _split(v):
    return [x.strip() for x in re.split(r"[,\n]+", str(v or "")) if x.strip()]


def _rule_targets(r, P, META):
    cats = {CATS.get(c) for c in _split(r.get("cats"))} - {None}
    tt, vals = r.get("target_type") or "전체", _split(r.get("target"))
    out = []
    for code, p in P.items():
        m = META[code]
        if cats and m["cat"] not in cats:
            continue
        if tt == "코드" and code not in vals:
            continue
        if tt == "특성" and not any(FEATURE_TARGETS[v](m) for v in vals if v in FEATURE_TARGETS):
            continue
        if tt == "명칭 포함" and not any(v in p[1] for v in vals):
            continue
        out.append(code)
    return out


def validate_rules(rules, P=None, META=None):
    errs, warns = [], []
    for i, r in enumerate(rules, 1):
        if str(r.get("on", "Y")).strip().upper() in ("N", "NO", "0"):
            continue
        tag = f"고객 기반 데이터 {i}행"
        q = r.get("field")
        if q not in QUESTION_OF:
            errs.append(f"{tag}: 질문 '{q}' 을(를) 알 수 없어요.")
            continue
        bad = [v for v in _split(r.get("values")) if v not in RULE_QUESTIONS[q]]
        if not _split(r.get("values")):
            errs.append(f"{tag}: 답을 하나 이상 골라 주세요.")
        if bad:
            errs.append(f"{tag}: '{q}' 질문에 없는 답이에요: {', '.join(bad)}")
        badc = [c for c in _split(r.get("cats")) if c not in CATS]
        if badc:
            errs.append(f"{tag}: 알 수 없는 구분: {', '.join(badc)}")
        tt = r.get("target_type") or "전체"
        if tt not in TARGET_TYPES:
            errs.append(f"{tag}: 대상 조건은 {'·'.join(TARGET_TYPES)} 중 하나예요.")
        elif tt != "전체" and not _split(r.get("target")):
            errs.append(f"{tag}: 대상 값을 입력해 주세요.")
        elif tt == "특성":
            badf = [v for v in _split(r.get("target")) if v not in FEATURE_TARGETS]
            if badf:
                errs.append(f"{tag}: 특성은 {', '.join(FEATURE_TARGETS)} 중에서 골라요: {', '.join(badf)}")
        if tt == "전체" and not _split(r.get("cats")):
            errs.append(f"{tag}: 대상 구분이나 대상 조건 중 하나는 정해 주세요.")
        if r.get("level") not in LEVELS:
            errs.append(f"{tag}: 등급은 우선 추천·추천·비추천·제외 중 하나예요.")
        if P is not None and not any(e.startswith(tag) for e in errs) and not _rule_targets(r, P, META):
            warns.append(f"{tag}: 조건에 맞는 제품이 없어 적용되지 않아요.")
    return errs, warns


def compile_rules(rules, P, META):
    out = []
    for r in rules:
        if str(r.get("on", "Y")).strip().upper() in ("N", "NO", "0") or r.get("field") not in QUESTION_OF:
            continue
        field = QUESTION_OF[r["field"]]
        label_to_key = {v: k for k, v in _opts(field).items()}
        keys = [label_to_key[v] for v in _split(r.get("values")) if v in label_to_key]
        codes = _rule_targets(r, P, META)
        if not keys or not codes or r.get("level") not in LEVELS:
            continue
        pts = LEVELS[r["level"]]
        out.append({"field": field, "values": keys, "codes": codes, **({"exclude": True} if pts is None else {"pts": pts})})
    return out
