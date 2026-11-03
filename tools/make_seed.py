"""v3 제품 데이터 → 데이터 관리 탭 초기값(app/seed/).

    python tools/make_seed.py <아이방플래너-v3 폴더> <세트단품_판매가.xlsx>

- seed.json: products / sales / features 행 + base(BR·REFERENCE_SIGNATURES·meta)
- images/<코드>.webp: v3 제품 사진
변환 결과를 compile_catalog 로 다시 만들어 원본 catalog 와 대조한다(가격·세트·판매량·특성).
"""
import base64
import csv
import json
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.catalog import BUNDLE_LABEL, CAT_LABEL, WALL_LABEL, compile_catalog, parse_bundle, validate  # noqa: E402

V3, XLSX = Path(sys.argv[1]), Path(sys.argv[2])
OUT = ROOT / "app" / "seed"


def yn(v):
    return "Y" if v else ""


def main():
    cat = json.loads((V3 / "src" / "catalog.json").read_text(encoding="utf-8"))
    images = json.loads((V3 / "src" / "images.json").read_text(encoding="utf-8"))
    P, M = cat["P"], cat["META"]

    unit = {}
    ws = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)["판매가"]
    for r in list(ws.iter_rows(values_only=True))[1:]:
        unit.setdefault(r[1], r[0])

    # 스마트스토어 링크·고객 기반 데이터는 손으로 채운 값이라 기존 seed.json 의 것을 유지
    prev = OUT / "seed.json"
    old = json.loads(prev.read_text(encoding="utf-8")) if prev.exists() else {}
    links = {r["code"]: r.get("naver_url", "") for r in old.get("products", [])}
    order = list(CAT_LABEL)
    products = []
    for code in sorted(P, key=lambda k: (order.index(M[k]["cat"]), k)):
        p, m = P[code], M[code]
        price = m["variants"][0]["price"] if m["priceKind"] != "reference" and m["variants"] else p[2]
        products.append({"unit": unit.get(code, "단품"), "cat": CAT_LABEL[m["cat"]], "code": code, "name": p[1],
                         "official_url": "", "price": price})
    for dk, d in cat["BUNDLES"].items():
        for ck, b in d.items():
            products.append({"unit": "세트", "cat": BUNDLE_LABEL, "code": b["code"], "name": b["name"],
                             "official_url": "", "price": b["variants"][0]["price"]})

    sales = []
    with open(V3 / "internal" / "sales_mapping.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            sales.append({"code": r["product_code"], "group": "일반" if r["group"] == "regular" else "모션",
                          "name": r["product_name"], "monthly": float(r["monthly_shipment"])})

    features = []
    for code in [r["code"] for r in products if r["cat"] != BUNDLE_LABEL]:
        m = M[code]
        features.append({
            "code": code, "tier": m["tier"] or "", "width": m["width"] or "", "depth": m["depth"] or "",
            "wall": WALL_LABEL[m["wall"]], "min_ceiling": m["minCeiling"] or "",
            "motion": yn(m["motion"]), "multi": yn(m["multi"]), "light": yn(m["light"]),
            "colors": ", ".join(v["color"] for v in m["variants"]) if m["priceKind"] != "reference" else "",
            "features": " | ".join(m["features"]), "checks": " | ".join(m["checks"]), "guide": "",
            "_carry": {"family": m["family"], "ceilingUncertain": m["ceilingUncertain"], "guideIds": m["guideIds"],
                       "sources": m["sources"], "priceKind": m["priceKind"]},
        })

    base = {"BR": cat["BR"], "REFERENCE_SIGNATURES": cat["REFERENCE_SIGNATURES"], "meta": cat["meta"]}
    rules = old.get("rules", [])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "images").mkdir(exist_ok=True)
    for code, uri in images.items():
        (OUT / "images" / f"{code}.webp").write_bytes(base64.b64decode(uri.split(",", 1)[1]))
    (OUT / "seed.json").write_text(json.dumps({"products": products, "sales": sales, "features": features, "rules": rules, "base": base},
                                              ensure_ascii=False, indent=1), encoding="utf-8")

    # ── 대조 ──
    errs, warns = validate(products, sales, features)
    built = compile_catalog(products, sales, features, base, set(images))
    bad = []
    for code, p in P.items():
        b, m, bm = built["P"].get(code), M[code], built["META"].get(code)
        if not b:
            bad.append(f"{code} 누락"); continue
        if (b[1], b[3], b[4]) != (p[1], p[3], p[4]):
            bad.append(f"{code} P {b[:5]} != {p[:5]}")
        for k in ("family", "cat", "tier", "width", "depth", "wall", "minCeiling", "motion", "multi", "light",
                  "features", "checks", "priceKind"):
            if bm[k] != m[k]:
                bad.append(f"{code} META.{k} {bm[k]!r} != {m[k]!r}")
        if m["priceKind"] != "reference" and [(v["color"], v["price"]) for v in bm["variants"]] != [(v["color"], v["price"]) for v in m["variants"]]:
            bad.append(f"{code} variants 불일치")
    pairs = {(d, c, b["code"], b["variants"][0]["price"]) for d, x in cat["BUNDLES"].items() for c, b in x.items()}
    bpairs = {(d, c, b["code"], b["variants"][0]["price"]) for d, x in built["BUNDLES"].items() for c, b in x.items()}
    sp = {k: (v["group"], v["rank"], v["priority"]) for k, v in cat["SALES_PRIORITY"].items()}
    bsp = {k: (v["group"], v["rank"], v["priority"]) for k, v in built["SALES_PRIORITY"].items()}
    print(f"products {len(products)} (단품·세트 제품 {len(P)}, 책상+의자 세트 {len(products) - len(P)}) | sales {len(sales)} | features {len(features)} | images {len(images)}")
    print(f"validate: errors {len(errs)} warnings {len(warns)}", errs[:3], warns[:3])
    print(f"P/META 불일치 {len(bad)}", bad[:5])
    print(f"세트 조합 원본 {len(pairs)} / 재구성 {len(bpairs)} / 일치 {len(pairs & bpairs)}", sorted(pairs - bpairs)[:3])
    print(f"판매량 우선순위 원본 {len(sp)} / 재구성 {len(bsp)} / 일치 {sum(sp.get(k) == v for k, v in bsp.items())}")


if __name__ == "__main__":
    main()
