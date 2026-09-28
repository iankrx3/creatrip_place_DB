"""페이지 HTML에 포함된 __NEXT_DATA__ (Apollo 캐시)를 꺼내고 참조를 따라가는 도구."""

import json
import re
from typing import Any

from .page_spec import NEXT_DATA_SCRIPT_ID

_NEXT_DATA_RE = re.compile(
    rf'<script id="{NEXT_DATA_SCRIPT_ID}"[^>]*>(.*?)</script>', re.S
)


def extract_apollo_state(html: str) -> dict[str, Any]:
    m = _NEXT_DATA_RE.search(html)
    if not m:
        raise ValueError("__NEXT_DATA__ not found")
    data = json.loads(m.group(1))
    return data["props"]["pageProps"].get("initialApolloState") or {}


class Apollo:
    """정규화된 Apollo 캐시를 읽기 쉽게 감싼다."""

    def __init__(self, state: dict[str, Any]):
        self.state = state

    def get(self, key: str) -> dict[str, Any] | None:
        return self.state.get(key)

    def deref(self, value: Any) -> Any:
        if isinstance(value, dict) and "__ref" in value:
            return self.state.get(value["__ref"])
        return value

    def deref_list(self, values: list | None) -> list[dict[str, Any]]:
        return [v for v in (self.deref(x) for x in (values or [])) if v]

    @staticmethod
    def field(obj: dict[str, Any] | None, prefix: str) -> Any:
        """`localizedDiscountPrice({...})` 처럼 인자가 붙은 키를 이름 접두어로 찾는다.

        prefix 에 인자 일부까지 넣으면 그 인자를 가진 키만 고른다.
        """
        if not obj:
            return None
        if prefix in obj:
            return obj[prefix]
        for k, v in obj.items():
            if k.startswith(prefix):
                return v
        return None

    def trans_name(self, obj: dict[str, Any] | None, language: str = "ENGLISH") -> str | None:
        trans = self.deref_list(self.field(obj, f'translations({{"language":"{language}"}})'))
        return trans[0].get("name") if trans else None

    def category_name(self, cat: dict[str, Any] | None) -> str | None:
        return self.trans_name(cat)
