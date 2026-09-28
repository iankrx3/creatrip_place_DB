"""상세 페이지: 하위 옵션을 펼친 뒤 Apollo 캐시와 화면 텍스트를 함께 가져온다."""

import logging
import time
from datetime import datetime, timezone

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait

from . import page_spec
from .driver import is_blocked
from .next_data import extract_apollo_state

log = logging.getLogger(__name__)

MAX_TOGGLE_CLICKS = 40


class BlockedError(RuntimeError):
    pass


def _expand_option_groups(driver: WebDriver) -> int:
    """접힌 'Select Options' 토글을 하나씩 연다. 같은 토글을 다시 누르면 접히므로 표시해 두고 건너뛴다."""
    clicked = 0
    for _ in range(MAX_TOGGLE_CLICKS):
        toggles = [
            t
            for t in driver.find_elements(By.XPATH, page_spec.COLLAPSED_OPTION_TOGGLE_XPATH)
            if t.get_attribute("data-cp-opened") != "1"
        ]
        if not toggles:
            break
        driver.execute_script(
            "arguments[0].setAttribute('data-cp-opened','1');"
            "arguments[0].scrollIntoView({block:'center'});"
            "arguments[0].click();",
            toggles[0],
        )
        clicked += 1
        time.sleep(1.2)
    return clicked


def slice_options_text(body_text: str) -> str:
    start = body_text.find(page_spec.OPTIONS_START)
    if start < 0:
        return ""
    ends = [i for m in page_spec.OPTIONS_END_MARKERS if (i := body_text.find(m, start)) > 0]
    return body_text[start : min(ends) if ends else len(body_text)]


def fetch_detail(driver: WebDriver, code: int) -> dict:
    url = page_spec.detail_url(code)
    driver.get(url)
    WebDriverWait(driver, 30).until(lambda d: d.execute_script("return document.readyState") == "complete")
    time.sleep(2)
    html = driver.page_source
    if is_blocked(html):
        raise BlockedError(f"blocked by CloudFront: {url}")
    state = extract_apollo_state(html)

    try:
        clicked = _expand_option_groups(driver)
    except WebDriverException as e:  # 옵션 펼치기는 실패해도 기본 정보는 저장한다
        log.warning("spot %s: option expand failed: %s", code, e)
        clicked = -1

    body_text = driver.find_element(By.TAG_NAME, "body").text
    return {
        "code": code,
        "url": url,
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "option_groups_expanded": clicked,
        "apollo_state": state,
        "options_text": slice_options_text(body_text),
        "body_text": body_text,
    }
