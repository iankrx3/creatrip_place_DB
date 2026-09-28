"""상세 페이지 원본(Apollo 캐시 + 화면 텍스트)을 data/raw/{code}.json.gz 로 보관한다.

정규화 규칙을 바꿨을 때 사이트를 다시 긁지 않고 재계산하기 위한 스냅샷이다.
"""

import gzip
import json
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def save_raw(raw: dict, raw_dir: Path = RAW_DIR) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{raw['code']}.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False)
    return path


def load_raw(code: int | str, raw_dir: Path = RAW_DIR) -> dict | None:
    path = raw_dir / f"{code}.json.gz"
    if not path.exists():
        return None
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def iter_raw(raw_dir: Path = RAW_DIR):
    for path in sorted(raw_dir.glob("*.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            yield json.load(f)
