"""places.json → places.csv / coverage.md 생성.

    python -m normalize.build            # 출력 파일만 다시 생성
    python -m normalize.build --from-raw # data/raw 스냅샷으로 모든 레코드를 다시 정규화 (규칙 수정 후)
"""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from scraper.raw_store import load_raw

from .config import DATA_DIR, categories_config
from .place import build_place
from .schema import Place

PLACES_JSON = DATA_DIR / "places.json"
PLACES_CSV = DATA_DIR / "places.csv"
COVERAGE_MD = DATA_DIR / "coverage.md"


def load_places(path: Path = PLACES_JSON) -> dict[int, dict]:
    if not path.exists():
        return {}
    return {int(p["id"]): p for p in json.loads(path.read_text(encoding="utf-8"))}


def save_places(places: dict[int, dict], path: Path = PLACES_JSON) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [Place.model_validate(places[k]).model_dump() for k in sorted(places)]
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _hours_str(hours: dict | None) -> str:
    if not hours:
        return ""
    return "; ".join(f"{d} " + (",".join(f"{a}-{b}" for a, b in v) or "closed") for d, v in hours.items())


def write_csv(places: dict[int, dict], path: Path = PLACES_CSV) -> None:
    cols = [
        "id", "name", "subtype", "extra_subtypes", "onboarding", "city", "region", "lat", "lng", "address",
        "nearest_station", "price_type", "price_min_usd", "deposit_usd", "languages", "duration_min", "hours",
        "closed_days", "fix_targets", "procedures", "downtime_grade", "downtime_days_max", "needs_before",
        "rating", "review_count", "active", "missing_fields", "url",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for k in sorted(places):
            p = places[k]
            st = p.get("nearest_station")
            w.writerow({
                **{c: p.get(c) for c in cols},
                "extra_subtypes": ";".join(p["extra_subtypes"]),
                "nearest_station": f"{st['name']} ({st.get('line') or ''}, {st.get('distance_m')}m)" if st else "",
                "languages": ";".join(f"{l['code']}:{l['level']}" for l in p["languages"]),
                "hours": _hours_str(p.get("hours")),
                "closed_days": ";".join(p["closed_days"]),
                "fix_targets": ";".join(p["fix_targets"]),
                "procedures": ";".join(
                    f"{x['key']}:{x['downtime_grade']}:{x['downtime_days_min']}-{x['downtime_days_max']}d"
                    for x in p["procedures"]
                ),
                "needs_before": ";".join(p["needs_before"]),
                "missing_fields": ";".join(p["missing_fields"]),
            })


# 온보딩 질문 → 채움 여부 판단
COVERAGE_ROWS = [
    ("FIX (skin / face)", "대표 subtype / 부가 subtype / 시술별 skin·face", [
        ("subtype", lambda p: bool(p["subtype"])),
        ("extra_subtypes", lambda p: bool(p["extra_subtypes"])),
        ("시술 target (피부과)", lambda p: p["subtype"] != "dermatology" or bool(p["fix_targets"])),
    ]),
    ("FIX 다운타임", "시술별 다운타임 등급·일수", [
        ("procedures", lambda p: bool(p["procedures"])),
        ("페이지 근거 다운타임", lambda p: any(x["downtime_source"] == "page" for x in p["procedures"])),
    ]),
    ("CHANGE / RESTORE", "대표 / 부가 카테고리", [
        ("onboarding", lambda p: bool(p["onboarding"])),
    ]),
    ("여행 기간", "다운타임 일수, 전날 먼저 받을 카테고리", [
        ("downtime_days_max", lambda p: p["downtime_days_max"] is not None),
        ("needs_before", lambda p: bool(p["needs_before"])),
    ]),
    ("도시 / 지역", "city, region, lat/lng", [
        ("city", lambda p: bool(p["city"])),
        ("region", lambda p: bool(p["region"])),
        ("lat/lng", lambda p: p["lat"] is not None and p["lng"] is not None),
    ]),
    ("예산 (1회 최대 USD)", "대표 가격", [
        ("price_min_usd", lambda p: p["price_min_usd"] is not None),
        ("deposit_usd (예약금만)", lambda p: p.get("deposit_usd") is not None),
    ]),
    ("언어", "지원 언어 + 출처/수준", [
        ("languages", lambda p: bool(p["languages"])),
        ("listed (명시)", lambda p: any(l["level"] == "listed" for l in p["languages"])),
    ]),
    ("루틴 시간표", "소요 시간(분), 요일별 영업시간", [
        ("duration_min", lambda p: p["duration_min"] is not None),
        ("hours", lambda p: bool(p["hours"])),
    ]),
    ("점수", "평점, 리뷰 수", [
        ("rating", lambda p: p["rating"] is not None),
        ("review_count", lambda p: p["review_count"] is not None),
    ]),
]


def write_coverage(places: dict[int, dict], path: Path = COVERAGE_MD) -> str:
    rows = list(places.values())
    n = len(rows)
    lines = [f"# 필드 채움 현황 ({n}곳)", "", "| 온보딩 질문 | 필요한 정보 | 필드 | 채워진 곳 |", "|---|---|---|---|"]
    for question, need, checks in COVERAGE_ROWS:
        for i, (label, fn) in enumerate(checks):
            filled = sum(1 for p in rows if fn(p))
            lines.append(f"| {question if i == 0 else ''} | {need if i == 0 else ''} | {label} | {filled} / {n} |")
    lines += ["", "## 카테고리별 장소 수", "", "| subtype | 장소 수 |", "|---|---|"]
    counts = Counter(p["subtype"] for p in rows)
    for key in categories_config()["categories"]:
        lines.append(f"| {key} | {counts.get(key, 0)} |")
    text = "\n".join(lines) + "\n"
    path.write_text(text, encoding="utf-8")
    return text


def rebuild_from_raw(places: dict[int, dict]) -> int:
    count = 0
    for code, p in places.items():
        raw = load_raw(code)
        if raw is None:
            continue
        new = build_place(raw, p["subtype"]).model_dump()
        new["extra_subtypes"] = sorted(set(new["extra_subtypes"]) | set(p["extra_subtypes"]))
        places[code] = new
        count += 1
    return count


def write_outputs(places: dict[int, dict]) -> str:
    save_places(places)
    write_csv(places)
    return write_coverage(places)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-raw", action="store_true")
    args = ap.parse_args()
    places = load_places()
    if args.from_raw:
        print(f"re-normalized {rebuild_from_raw(places)} places from raw snapshots")
    print(write_outputs(places))


if __name__ == "__main__":
    main()
