"""creatrip 장소 수집 실행.

    python -m scraper                                   # 카테고리마다 새 장소 10곳
    python -m scraper --categories dermatology,sauna --per-category 3
    python -m scraper --refresh                         # 이미 저장된 장소를 다시 수집
"""

import argparse
import json
import logging
import os
import time
from datetime import datetime, timezone

from selenium.common.exceptions import WebDriverException

from normalize.build import load_places, write_outputs
from normalize.config import DATA_DIR, categories_config
from normalize.place import build_place

from . import page_spec
from .detail_page import BlockedError, fetch_detail
from .driver import is_blocked, make_driver, polite_sleep
from .list_page import parse_list_page
from .raw_store import save_raw

log = logging.getLogger("scraper")
FAILED_JSON = DATA_DIR / "failed.json"
MAX_LIST_PAGES = 20
RETRIES = 3


def _load_failed() -> list[dict]:
    return json.loads(FAILED_JSON.read_text(encoding="utf-8")) if FAILED_JSON.exists() else []


def _save_failed(failed: list[dict]) -> None:
    FAILED_JSON.write_text(json.dumps(failed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _get(driver, url: str) -> str:
    driver.get(url)
    time.sleep(2)
    html = driver.page_source
    if is_blocked(html):
        raise BlockedError(f"blocked by CloudFront: {url}")
    return html


def pick_new_codes(driver, key: str, cfg: dict, places: dict, n: int, preset: list[int]) -> list[int]:
    """조회수 순 목록을 넘기며 아직 저장되지 않은 코드를 n개 고른다. 이미 저장된 장소는 부가 subtype만 추가한다."""
    picked = list(preset[:n])
    for page in range(1, MAX_LIST_PAGES + 1):
        if len(picked) >= n:
            break
        lp = parse_list_page(_get(driver, page_spec.list_url(cfg["category"], page, cfg.get("middle"))))
        log.info("[%s] list page %d: %d spots (total %d)", key, page, len(lp.codes), lp.total)
        for code in lp.codes:
            if code in places:
                p = places[code]
                if p["subtype"] != key and key not in p["extra_subtypes"]:
                    p["extra_subtypes"] = sorted(p["extra_subtypes"] + [key])
                continue
            if code not in picked and len(picked) < n:
                picked.append(code)
        if not lp.codes or page * page_spec.LIST_PAGE_SIZE >= lp.total:
            break
        polite_sleep()
    return picked


def scrape_one(driver, code: int, key: str) -> dict:
    last = None
    for attempt in range(RETRIES):
        try:
            raw = fetch_detail(driver, code)
            save_raw(raw)
            return build_place(raw, key).model_dump()
        except (WebDriverException, BlockedError, ValueError) as e:
            last = e
            wait = 5 * 2**attempt
            log.warning("spot %s attempt %d failed (%s); retry in %ss", code, attempt + 1, e, wait)
            time.sleep(wait)
    raise RuntimeError(f"spot {code}: {last}")


def main() -> None:
    cfg_all = categories_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--categories", default="", help="쉼표로 구분한 subtype (기본: 전체)")
    ap.add_argument("--per-category", type=int, default=cfg_all["per_category"])
    ap.add_argument("--refresh", action="store_true", help="새 장소 대신 이미 저장된 장소를 다시 수집")
    ap.add_argument("--no-headless", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    keys = [k.strip() for k in args.categories.split(",") if k.strip()] or list(cfg_all["categories"])
    unknown = set(keys) - set(cfg_all["categories"])
    if unknown:
        raise SystemExit(f"unknown categories: {sorted(unknown)}")

    places = load_places()
    failed = _load_failed()
    summary = {"added": [], "refreshed": [], "failed": []}
    driver = make_driver(headless=not args.no_headless)
    try:
        for key in keys:
            cfg = cfg_all["categories"][key]
            if args.refresh:
                codes = sorted(c for c, p in places.items() if p["subtype"] == key)
            else:
                retry = [f["code"] for f in failed if f["subtype"] == key]
                codes = pick_new_codes(driver, key, cfg, places, args.per_category, retry)
            log.info("[%s] %d spots to scrape: %s", key, len(codes), codes)

            for code in codes:
                polite_sleep()
                failed = [f for f in failed if f["code"] != code]
                try:
                    place = scrape_one(driver, code, key)
                except RuntimeError as e:
                    log.error("%s", e)
                    failed.append({"code": code, "subtype": key, "error": str(e)[:300],
                                   "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
                    summary["failed"].append(code)
                    continue
                if code in places:
                    old = places[code]
                    place["subtype"] = old["subtype"]
                    place["extra_subtypes"] = sorted(set(place["extra_subtypes"]) | set(old["extra_subtypes"]))
                    summary["refreshed"].append(code)
                else:
                    summary["added"].append(code)
                places[code] = place
                log.info("[%s] saved %s %s (missing: %s)", key, code, place["name"], place["missing_fields"])

            # 카테고리마다 중간 저장 (실행이 중간에 끊겨도 결과 보존)
            write_outputs(places)
            _save_failed(failed)
    finally:
        driver.quit()

    coverage = write_outputs(places)
    _save_failed(failed)
    report = (
        f"added {len(summary['added'])}, refreshed {len(summary['refreshed'])}, failed {len(summary['failed'])}"
        f" (total {len(places)} places)\n\n{coverage}"
    )
    print(report)
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(path, "a", encoding="utf-8") as f:
            f.write(report)
    (DATA_DIR / "last_run.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
