from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"


@lru_cache
def categories_config() -> dict:
    return yaml.safe_load((CONFIG_DIR / "categories.yaml").read_text(encoding="utf-8"))


@lru_cache
def procedures_config() -> dict:
    return yaml.safe_load((CONFIG_DIR / "procedures.yaml").read_text(encoding="utf-8"))["procedures"]


def category_code_to_subtype() -> dict[int, str]:
    """creatrip 카테고리 코드 → subtype. middle 이 있으면 middle 코드, 없으면 main 코드로 매핑한다."""
    out = {}
    for key, c in categories_config()["categories"].items():
        out[int(c.get("middle") or c["category"])] = key
    return out
