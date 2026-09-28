"""headless Chrome 생성과 요청 간 딜레이."""

import logging
import random
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

log = logging.getLogger(__name__)


def make_driver(headless: bool = True) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1400,3000")
    opts.add_argument("--lang=en-US")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(60)

    # CloudFront가 "HeadlessChrome" UA를 403으로 막으므로, 실제 브라우저 버전은 유지한 채 UA만 일반 Chrome으로 바꾼다.
    ua = driver.execute_script("return navigator.userAgent").replace("HeadlessChrome", "Chrome")
    driver.execute_cdp_cmd("Network.setUserAgentOverride", {"userAgent": ua, "acceptLanguage": "en-US,en"})
    log.info("user agent: %s", ua)
    return driver


def polite_sleep(min_s: float = 1.0, max_s: float = 3.0) -> None:
    time.sleep(random.uniform(min_s, max_s))


def is_blocked(page_source: str) -> bool:
    return "The request could not be satisfied" in page_source[:3000]
