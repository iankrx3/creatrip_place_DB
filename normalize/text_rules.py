"""화면 텍스트를 해석하는 규칙들: 가격, 소요시간, 하위 옵션, 언어."""

import html
import re

# 부가 상품(짐 보관, 락커 등)은 소요시간·최저가 계산에서 뺀다
ADDON_OPTION_RE = re.compile(r"luggage|storage|locker|parking|towel rental|shipping|delivery", re.I)


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<(br|/p|/li|/div|/h\d)[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[ \t]+", " ", html.unescape(text)).strip()


# ---------------------------------------------------------------- 가격

_PRICE_RE = re.compile(
    r"^(?:\[(?P<pct>\d+)%\]\s*)?(?:Deposit\s+)?(?:From\s+)?(?P<amount>[\d,]+(?:\.\d+)?)\s*(?P<cur>USD|KRW|₩)$"
)


def parse_price_line(line: str) -> tuple[float, bool, str] | None:
    """'[50%] 103.09 USD' → (103.09, True, 'USD'). 'Free' → (0, False, 'USD'). 가격 줄이 아니면 None."""
    line = line.strip()
    if line == "Free":
        return 0.0, False, "USD"
    m = _PRICE_RE.match(line)
    if not m:
        return None
    cur = "KRW" if m["cur"] in ("KRW", "₩") else "USD"
    return float(m["amount"].replace(",", "")), m["pct"] is not None, cur


# ---------------------------------------------------------------- 소요시간

_RANGE_MIN_RE = re.compile(r"(\d+)\s*(?:~|-|–|to|至)\s*(\d+)\s*(?:minutes?|mins?|min|분|分鐘|分钟)", re.I)
_MIN_RE = re.compile(r"(\d+)\s*(?:minutes?|mins?|min|분|分鐘|分钟)\b", re.I)
_HOUR_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h|시간)\b(?:\s*(\d+)\s*(?:minutes?|mins?|m|분)\b)?", re.I)


def parse_duration_min(*texts: str | None) -> int | None:
    """'(60 minutes)' → 60, '30至40分鐘' → 40, '1h 30m' → 90. 범위는 긴 쪽을 쓴다 (일정 배치에 안전).

    옵션명 → 설명 순서로 본다. 옵션명이 'InMode FX 5min | 10 min' 처럼 구분자로 끝나면 마지막 구간을 먼저 본다.
    """
    for text in texts:
        if not text:
            continue
        parts = re.split(r"\s*[|ㅣ]\s*", text)
        for candidate in ([parts[-1]] if len(parts) > 1 else []) + [text]:
            if (minutes := _duration_in(candidate)) is not None:
                return minutes
    return None


def _duration_in(text: str) -> int | None:
    if m := _RANGE_MIN_RE.search(text):
        return int(m.group(2))
    if m := _HOUR_RE.search(text):
        return round(float(m.group(1)) * 60) + int(m.group(2) or 0)
    if m := _MIN_RE.search(text):
        return int(m.group(1))
    return None


# ---------------------------------------------------------------- 하위 옵션 (펼친 화면 텍스트)

_NOISE_LINES = {
    "Select an option", "Show with KRW", "Show with USD", "SELECT", "HOT", "NEW", "BEST", "Option",
    "Select Options", "MORE DETAILS", "Sold out", "SOLD OUT", "Please select a date.", "Select date",
}
_NOISE_RE = re.compile(r"(PICK$|^Membership price|^\d+%$|^👤|^Only \d+ left)")


def _is_noise(line: str) -> bool:
    return not line or line in _NOISE_LINES or bool(_NOISE_RE.search(line))


def parse_child_options(options_text: str, group_names: set[str]) -> list[dict]:
    """펼친 옵션 텍스트에서 하위 옵션(그룹 안의 시술)을 뽑는다.

    화면 순서: 그룹명 → Select Options → 시술명 → [할인%] 판매가 USD → 정가 USD → … → SELECT
    그룹명이 아닌 루트 옵션(가격이 __NEXT_DATA__ 에 있음)은 여기서 다루지 않는다.
    """
    children: list[dict] = []
    group: str | None = None
    current: dict | None = None
    for raw in options_text.splitlines():
        line = raw.strip()
        if line in group_names:
            group, current = line, None
            continue
        if line == "SELECT":
            group, current = None, None
            continue
        if group is None or _is_noise(line):
            continue
        price = parse_price_line(line)
        if price is not None:
            if current is None:
                continue
            amount, is_sale, cur = price
            if cur == "KRW":
                current.setdefault("price_krw", int(amount))
            elif current.get("price_usd") is None:
                current["price_usd"] = amount
            elif amount > current["price_usd"]:
                current["original_price_usd"] = amount
            continue
        current = {"name": line, "group": group, "price_usd": None}
        children.append(current)
    return children


# ---------------------------------------------------------------- 언어

LANGUAGE_CODES = {
    "english": "en", "japanese": "ja", "日本語": "ja", "chinese": "zh", "中文": "zh", "简体中文": "zh",
    "繁體中文": "zh", "korean": "ko", "한국어": "ko", "thai": "th", "ไทย": "th", "vietnamese": "vi",
    "tiếng việt": "vi", "spanish": "es", "español": "es", "french": "fr", "français": "fr",
    "german": "de", "deutsch": "de", "russian": "ru", "русский": "ru", "mongolian": "mn",
    "монгол": "mn", "indonesian": "id", "bahasa indonesia": "id", "arabic": "ar", "italian": "it",
    "italiano": "it", "cantonese": "zh",
}
_ENGLISH_LANG_NAMES = [k for k in LANGUAGE_CODES if k.isascii() and " " not in k]
_MENTION_RE = re.compile(
    r"\b(" + "|".join(_ENGLISH_LANG_NAMES) + r")\b[^.\n]{0,80}?\b(interpret\w*|speak\w*|speaking|staff|support\w*|available|consultation|translator)",
    re.I,
)
# 모든 상세 페이지에 공통으로 붙는 Creatrip 고객센터 문구는 장소의 언어 지원이 아니다
_PLATFORM_LINES = ("24/7 English/Chinese Support", "Immediate help anytime")


def language_code(name: str) -> str | None:
    return LANGUAGE_CODES.get(name.strip().lower())


def available_languages_section(body_text: str, heading: str) -> list[str]:
    lines = body_text.splitlines()
    try:
        i = lines.index(heading)
    except ValueError:
        return []
    out = []
    for line in lines[i + 1 : i + 12]:
        if language_code(line) is None:
            break
        out.append(line.strip())
    return out


def mentioned_languages(body_text: str) -> list[str]:
    names = []
    for line in body_text.splitlines():
        if any(p in line for p in _PLATFORM_LINES):
            continue
        for m in _MENTION_RE.finditer(line):
            names.append(m.group(1))
        # "Japanese, Chinese, and English interpretation is available." 처럼 나열된 경우
        if re.search(r"interpret|translat|speak|communicat|available in", line, re.I):
            names += [w for w in re.findall(r"[A-Za-z]+", line) if w.lower() in _ENGLISH_LANG_NAMES]
    return names


# ---------------------------------------------------------------- 다운타임 문장

_DOWNTIME_SENT_RE = re.compile(r"[^.\n]*\b(downtime|recovery period|scab\w*|swelling|bruis\w*|redness)\b[^.\n]*[.\n]?", re.I)
_DAYS_RE = re.compile(r"(\d+)\s*(?:~|-|–|to)\s*(\d+)\s*days?|(\d+)\s*days?", re.I)


def precautions_section(body_text: str) -> str:
    """상세 페이지의 'Things To Keep In Mind' 영역만 잘라낸다 (리뷰·추천 카드 문구 제외)."""
    start = body_text.find("Things To Keep In Mind")
    if start < 0:
        return ""
    end = body_text.find("Store Info", start)
    return body_text[start : end if end > 0 else start + 5000]


def downtime_sentences(text: str) -> list[str]:
    seen, out = set(), []
    for m in _DOWNTIME_SENT_RE.finditer(text):
        s = m.group(0).strip()
        if s and s not in seen and len(s) < 300:
            seen.add(s)
            out.append(s)
    return out


def days_in_sentence(sentence: str) -> tuple[int, int] | None:
    if re.search(r"\bno downtime\b|\bwithout downtime\b|\bzero downtime\b", sentence, re.I):
        return 0, 0
    m = _DAYS_RE.search(sentence)
    if not m or not re.search(r"downtime|recover|heal|scab|swelling|bruis", sentence, re.I):
        return None
    if m.group(1):
        return int(m.group(1)), int(m.group(2))
    return int(m.group(3)), int(m.group(3))
