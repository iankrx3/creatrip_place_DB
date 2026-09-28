"""상세 페이지 원본(raw) → Place 레코드."""

import hashlib
import json
import re

from scraper.next_data import Apollo
from scraper.page_spec import AVAILABLE_LANGUAGES_HEADING

from .config import categories_config, category_code_to_subtype
from .procedure import GRADE_ORDER, build_procedures
from .schema import Language, Option, Place, Station
from .text_rules import (
    ADDON_OPTION_RE, strip_html, available_languages_section, downtime_sentences, language_code, mentioned_languages,
    parse_child_options, parse_duration_min, precautions_section,
)

DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
USD_EN = '({"input":{"currency":"USD","language":"ENGLISH"}})'
KRW_KO = '({"input":{"currency":"KRW","language":"KOREAN"}})'
KEY_FIELDS = ["region", "lat", "lng", "price_min_usd", "languages", "duration_min", "hours", "rating", "procedures"]


def _categories(ap: Apollo, spot: dict, types: str) -> list[dict]:
    return ap.deref_list(Apollo.field(spot, f'categories({{"types":{types}}})'))


def _options(ap: Apollo, spot: dict, options_text: str) -> list[Option]:
    roots = ap.deref_list(Apollo.field(spot, 'items({"input":{"isReservable":true,"isRoot":true}})'))
    options, group_names = [], set()
    for item in roots:
        trans = ap.deref_list(Apollo.field(item, 'translations({"language":"ENGLISH"})'))
        if not trans:
            continue
        name = (trans[0].get("name") or "").strip()
        desc = (trans[0].get("description") or "").strip() or None
        if Apollo.field(item, "children("):
            group_names.add(name)
            continue
        sale = Apollo.field(item, "localizedDiscountPrice" + USD_EN)
        orig = Apollo.field(item, "localizedOriginalPrice" + USD_EN)
        options.append(Option(
            name=name, description=desc,
            price_usd=sale, original_price_usd=orig if orig and sale is not None and orig > sale else None,
            price_krw=Apollo.field(item, "localizedDiscountPrice" + KRW_KO),
            duration_min=parse_duration_min(name, desc),
        ))
    for child in parse_child_options(options_text, group_names):
        options.append(Option(**child, duration_min=parse_duration_min(child["name"])))
    # 하위 옵션을 못 읽은 그룹도 이름은 남겨 시술 매칭에 쓴다
    parsed_groups = {o.group for o in options if o.group}
    for g in sorted(group_names - parsed_groups):
        options.append(Option(name=g, group=g, duration_min=parse_duration_min(g)))
    return options


def _hours(ap: Apollo, spot: dict) -> tuple[dict | None, list[str]]:
    entries = ap.deref_list(Apollo.field(spot, "spotOpeningHours({") or spot.get("spotOpeningHours"))
    if not entries:
        return None, []
    by_day = {h["dayOfWeek"]: h for h in entries[0].get("openingHours") or []}
    if not by_day:
        return None, []
    hours, closed = {}, []
    for day, key in zip(DAYS, DAY_KEYS):
        h = by_day.get(day)
        if h is None:
            continue
        periods = [[p["start"], p["end"]] for p in h.get("timePeriods") or []] if h.get("isOpen") else []
        hours[key] = periods
        if not periods:
            closed.append(key)
    return hours, closed


def _languages(ap: Apollo, spot: dict, body_text: str) -> list[Language]:
    found: dict[str, Language] = {}

    def add(name: str, source: str, level: str):
        code = language_code(name)
        if code and (code not in found or (found[code].level == "mentioned" and level == "listed")):
            found[code] = Language(code=code, name=name, source=source, level=level)

    for name in available_languages_section(body_text, AVAILABLE_LANGUAGES_HEADING):
        add(name, "available_languages", "listed")
    policy = ap.deref(spot.get("reservationPolicy"))
    for remark in ap.deref_list((policy or {}).get("remarks")):
        if remark.get("icon") == "LANGUAGE_ICON":
            label = ap.trans_name(remark) or ""
            if m := re.match(r"(.+?) Available$", label):
                add(m.group(1), "remark", "listed")
    for name in mentioned_languages(body_text):
        add(name, "text", "mentioned")
    return sorted(found.values(), key=lambda l: l.code)


def _nearest_station(ap: Apollo, spot: dict) -> Station | None:
    best = None
    for link in ap.deref_list(spot.get("subwayCategories")):
        cat = ap.deref(link.get("category"))
        if not cat:
            continue
        name = (ap.deref(Apollo.field(cat, "translation(")) or {}).get("name")
        line_cat = ap.deref(cat.get("parent")) or {}
        line = line_cat.get("alias") or (ap.deref(Apollo.field(line_cat, "translation(")) or {}).get("name")
        dist = link.get("distance") or ""
        m = re.match(r"([\d.]+)\s*(k?m)", dist)
        meters = round(float(m.group(1)) * (1000 if m.group(2) == "km" else 1)) if m else None
        if name and (best is None or (meters is not None and (best.distance_m is None or meters < best.distance_m))):
            best = Station(name=name, line=line, distance_m=meters)
    return best


def _price(spot: dict, options: list[Option], krw_per_usd: float) -> dict:
    alt = spot.get("priceAlternativeTextType") or ""
    paid = [o.price_usd for o in options if o.price_usd]
    if "DEPOSIT" in alt:
        deposit = Apollo.field(spot, "localizedDiscountPrice" + USD_EN) or None
        if deposit is None and spot.get("priceAlternativeTextValue"):
            deposit = round(spot["priceAlternativeTextValue"] / krw_per_usd, 2)
        # 예약금은 실제 시술 가격이 아니므로 예산 판단용 최저가는 비워 둔다
        return {"price_type": "deposit", "deposit_usd": deposit, "price_min_usd": None, "price_krw": None}
    if alt == "FREE_RESERVATION":
        return {"price_type": "free_reservation", "price_min_usd": min(paid) if paid else None, "price_krw": None}
    if spot.get("isFreeOfCharge") and not paid:
        return {"price_type": "free", "price_min_usd": 0.0, "price_krw": 0}
    base = Apollo.field(spot, "localizedDiscountPrice" + USD_EN)
    price = min(paid) if paid else base
    return {"price_type": "paid", "price_min_usd": price, "price_krw": spot.get("discountPrice")}


def build_place(raw: dict, subtype: str) -> Place:
    ap = Apollo(raw["apollo_state"])
    code = int(raw["code"])
    spot = ap.get(f"Spot:{code}")
    if spot is None:
        raise ValueError(f"Spot:{code} not in apollo state")
    cfg = categories_config()

    en = ap.deref_list(Apollo.field(spot, 'translations({"language":"ENGLISH"})'))
    ko = ap.deref_list(Apollo.field(spot, 'translations({"language":"KOREAN"})'))
    en = en[0] if en else {}
    ko = ko[0] if ko else {}

    # 카테고리
    code_map = category_code_to_subtype()
    main_mid = _categories(ap, spot, '["MAIN_RESERVATION","MIDDLE_RESERVATION"')
    if not main_mid:
        main_mid = _categories(ap, spot, '["MAIN_RESERVATION"]') + _categories(ap, spot, '["MIDDLE_RESERVATION"]')
    category_path = [n for c in main_mid if (n := ap.category_name(c))]
    extra = sorted({code_map[int(c["code"])] for c in main_mid if int(c["code"]) in code_map} - {subtype})

    loc = {c["type"]: ap.category_name(c) for c in _categories(ap, spot, '["CITY","DETAIL_LOCATION"]')}

    options = _options(ap, spot, raw.get("options_text") or "")
    body = raw.get("body_text") or ""
    precautions = "\n".join(
        strip_html(t) for t in [en.get("precautions"), en.get("howToUseText"), precautions_section(body)] if t
    )
    notes = downtime_sentences(precautions + "\n" + (raw.get("options_text") or ""))
    description = "\n".join(strip_html(t) for t in [en.get("moreInformation"), en.get("seoDescription")] if t)
    procedures = build_procedures(options, subtype, notes, description)
    hours, closed = _hours(ap, spot)
    services = [o for o in options if not ADDON_OPTION_RE.search(f"{o.group or ''} {o.name}")]
    durations = [o.duration_min for o in services if o.duration_min]
    review = spot.get("integratedReviewSummary") or {}

    place = Place(
        id=code,
        url=raw["url"],
        name=(en.get("name") or "").strip(),
        name_ko=ko.get("placeOfficialName") or ko.get("name"),
        active=bool(spot.get("isInBusiness", True)) and not spot.get("isSoldOut", False),
        subtype=subtype,
        extra_subtypes=extra,
        onboarding=cfg["categories"][subtype].get("onboarding"),
        category_path=category_path,
        procedures=procedures,
        fix_targets=sorted({p.target for p in procedures if p.target in ("skin", "face")}),
        downtime_grade=max((p.downtime_grade for p in procedures), key=GRADE_ORDER.get, default=None),
        downtime_days_max=max((p.downtime_days_max for p in procedures), default=None),
        needs_before=cfg["categories"][subtype].get("needs_before", []),
        downtime_notes=notes[:10],
        city=loc.get("CITY"),
        region=loc.get("DETAIL_LOCATION"),
        lat=spot.get("latitude"),
        lng=spot.get("longitude"),
        address=spot.get("address"),
        nearest_station=_nearest_station(ap, spot),
        telephone=spot.get("telephone"),
        **_price(spot, services, cfg["krw_per_usd"]),
        options=options,
        languages=_languages(ap, spot, body),
        duration_min=durations[0] if durations else None,
        hours=hours,
        closed_days=closed,
        rating=review.get("reviewRatingAverage", spot.get("reviewRatingAverage")),
        review_count=review.get("totalCount", spot.get("reviewCount")),
        view_count=spot.get("viewCount"),
        scraped_at=raw["scraped_at"],
    )
    return finalize(place)


def finalize(place: Place) -> Place:
    data = place.model_dump()
    place.missing_fields = [f for f in KEY_FIELDS if data.get(f) in (None, [], {})]
    data = place.model_dump(exclude={"scraped_at", "content_hash"})
    place.content_hash = hashlib.sha1(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    return place
