"""실제 페이지에서 저장한 스냅샷(tests/fixtures)으로 파싱·정규화를 검증한다. 네트워크를 쓰지 않는다."""

import gzip
import json
from pathlib import Path

import pytest

from normalize.place import build_place
from scraper.list_page import parse_list_page

FIXTURES = Path(__file__).parent / "fixtures"


def raw(code: int) -> dict:
    with gzip.open(FIXTURES / f"{code}.json.gz", "rt", encoding="utf-8") as f:
        return json.load(f)


def test_list_page_returns_ranked_codes_without_ads():
    html = gzip.open(FIXTURES / "list_dermatology.html.gz", "rt", encoding="utf-8").read()
    page = parse_list_page(html)
    assert page.total == 95
    assert len(page.codes) == 24
    assert page.codes[0] == 13214
    assert 14985 not in page.codes  # AD 카드


@pytest.fixture(scope="module")
def derm():
    return build_place(raw(13214), "dermatology")


def test_derm_location_and_score(derm):
    assert (derm.city, derm.region) == ("Seoul", "Gangnam")
    assert derm.lat == pytest.approx(37.523, abs=0.01) and derm.lng == pytest.approx(127.04, abs=0.01)
    assert derm.rating and derm.review_count and derm.review_count > 100
    assert derm.nearest_station and derm.nearest_station.distance_m


def test_derm_hours_include_closed_sunday(derm):
    assert derm.hours["mon"] == [["10:00", "19:00"]]
    assert derm.hours["sun"] == []
    assert derm.closed_days == ["sun"]


def test_derm_child_options_and_price(derm):
    hifu = next(o for o in derm.options if "HIFU Package" in o.name)
    assert hifu.price_usd == pytest.approx(103.09)
    assert hifu.group.startswith("[Creatrip Exclusive Package] Sagging")
    assert derm.price_type == "free_reservation"
    assert derm.price_min_usd == pytest.approx(103.09)  # 무료 상담 옵션(0원)은 최저가에서 제외


def test_derm_procedures_targets_and_downtime(derm):
    keys = {p.key for p in derm.procedures}
    assert {"hifu", "skin_booster", "microneedle"} <= keys
    assert derm.fix_targets == ["face", "skin"]
    booster = next(p for p in derm.procedures if p.key == "skin_booster")
    assert (booster.target, booster.downtime_grade, booster.downtime_source) == ("skin", "low", "dictionary")
    assert derm.downtime_days_max >= 3


def test_derm_languages_listed_and_mentioned(derm):
    levels = {l.code: l.level for l in derm.languages}
    assert levels["en"] == levels["zh"] == levels["ja"] == "listed"
    assert levels.get("ar") == "mentioned"


def test_deposit_clinic_has_no_confirmed_price():
    p = build_place(raw(13573), "dermatology")
    assert p.price_type == "deposit"
    assert p.price_min_usd is None and p.deposit_usd == pytest.approx(14.73)
    assert "price_min_usd" in p.missing_fields


def test_sauna_ignores_luggage_option_and_uses_default_procedure():
    p = build_place(raw(13261), "sauna")
    assert p.onboarding == "RESTORE"
    assert p.duration_min is None  # 24시간 짐 보관 옵션은 소요시간이 아니다
    assert p.price_min_usd and p.price_min_usd < 15
    assert {"sauna", "body_scrub"} <= {x.key for x in p.procedures}
    assert p.downtime_grade == "none"


def test_content_hash_is_stable():
    a = build_place(raw(13261), "sauna")
    b = build_place(raw(13261), "sauna")
    assert a.content_hash == b.content_hash
