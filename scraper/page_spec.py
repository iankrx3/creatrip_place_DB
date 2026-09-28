"""사이트 구조에 의존하는 값(URL, 화면 문구, XPath)을 한곳에 모은다.

creatrip 화면이 바뀌면 이 파일만 고치면 되도록 유지한다.
"""

BASE_URL = "https://creatrip.com"
LANG_PATH = "/en"

LIST_PAGE_SIZE = 24  # 목록 페이지당 spot 수 (광고 카드 제외)


def list_url(category: int, page: int, middle: int | None = None) -> str:
    url = f"{BASE_URL}{LANG_PATH}/spot/list?page={page}&category={category}&order=MOST_VIEWED_IN_A_MONTH"
    if middle is not None:
        url += f"&middleCategory={middle}&direction=DESC"
    return url


def detail_url(code: int | str) -> str:
    return f"{BASE_URL}{LANG_PATH}/spot/{code}"


# 페이지에 서버 렌더링으로 포함된 Next.js 데이터
NEXT_DATA_SCRIPT_ID = "__NEXT_DATA__"

# 옵션 영역 문구
OPTIONS_START = "Select an option"
OPTIONS_END_MARKERS = ("Reservation Info", "Cancellation & Refund Policy", "Things To Keep In Mind", "Store Info")
# 하위 옵션을 펼치는 토글: <span>Select Options</span><span direction="down">…</span>
COLLAPSED_OPTION_TOGGLE_XPATH = (
    "//span[normalize-space(text())='Select Options']"
    "[following-sibling::span[@direction='down']]"
)

# 가능 언어 섹션 제목
AVAILABLE_LANGUAGES_HEADING = "Available Languages"
