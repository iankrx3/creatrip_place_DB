"""옵션 이름/설명을 시술 사전(config/procedures.yaml)에 맞춰 시술별 대상·다운타임을 정한다."""

import re
from functools import lru_cache

from .config import procedures_config
from .schema import Option, Procedure
from .text_rules import days_in_sentence

GRADE_ORDER = {"none": 0, "low": 1, "high": 2}

# 옵션에서 시술을 못 찾았을 때 subtype 으로 기본 시술을 정한다 (피부과는 기본값 없음 = 모름)
SUBTYPE_DEFAULT_PROCEDURE = {
    "personal_color": "personal_color",
    "hair_salon": "hair_cut_style",
    "makeup": "makeup",
    "photo_studio": "photo",
    "nail_art": "nail",
    "sauna": "sauna",
    "body_scrub": "body_scrub",
    "massage": "massage",
    "yoga_wellness": "yoga_wellness",
}


def _compile(keywords: list[str]) -> re.Pattern:
    alts = "|".join(re.escape(k) for k in sorted(keywords, key=len, reverse=True))
    # 단어 단위로만 매칭 (photo ≠ Photon), 복수형 s/es 허용
    return re.compile(rf"(?<![A-Za-z])(?:{alts})(?:e?s)?(?![A-Za-z])", re.I)


@lru_cache
def _patterns(subtype: str | None) -> list[tuple[str, re.Pattern]]:
    out = []
    for key, p in procedures_config().items():
        if subtype in p.get("exclude_subtypes", []):
            continue
        keywords = p["keywords"] + p.get("subtype_keywords", {}).get(subtype, [])
        out.append((key, _compile(keywords)))
    return out


def match_procedure_keys(text: str, subtype: str | None = None) -> list[str]:
    return [key for key, pat in _patterns(subtype) if pat.search(text)]


def _grade_for_days(days_max: int) -> str:
    return "none" if days_max == 0 else "low" if days_max <= 2 else "high"


def _from_dictionary(key: str, source: str) -> Procedure:
    p = procedures_config()[key]
    lo, hi = p["downtime_days"]
    return Procedure(
        key=key, target=p["target"], downtime_grade=p["downtime_grade"],
        downtime_days_min=lo, downtime_days_max=hi, downtime_source=source,
    )


def build_procedures(
    options: list[Option], subtype: str, downtime_sentences: list[str], description: str = ""
) -> list[Procedure]:
    found: dict[str, Procedure] = {}
    for opt in options:
        text = " ".join(filter(None, [opt.group, opt.name, opt.description]))
        for key in match_procedure_keys(text, subtype):
            proc = found.setdefault(key, _from_dictionary(key, "dictionary"))
            if opt.name not in proc.matched_options:
                proc.matched_options.append(opt.name)

    # 피부과처럼 기본 시술이 없는데 옵션이 '예약금 / 상담 후 결정' 뿐이면 장소 소개문에서 시술을 찾는다
    if not found and description and subtype not in SUBTYPE_DEFAULT_PROCEDURE:
        for key in match_procedure_keys(description, subtype):
            proc = _from_dictionary(key, "dictionary")
            proc.matched_options = ["(place description)"]
            found[key] = proc

    if not found and subtype in SUBTYPE_DEFAULT_PROCEDURE:
        key = SUBTYPE_DEFAULT_PROCEDURE[subtype]
        found[key] = _from_dictionary(key, "subtype_default")

    # 페이지 문장이 특정 시술의 다운타임을 명시하면 사전 값을 덮어쓴다
    for sentence in downtime_sentences:
        days = days_in_sentence(sentence)
        if days is None:
            continue
        for key in match_procedure_keys(sentence, subtype):
            if key in found:
                proc = found[key]
                proc.downtime_days_min, proc.downtime_days_max = days
                proc.downtime_grade = _grade_for_days(days[1])
                proc.downtime_source = "page"
    return list(found.values())
