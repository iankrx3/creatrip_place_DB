"""카테고리 목록 페이지: 조회수 순 spot 코드와 전체 개수."""

from dataclasses import dataclass

from .next_data import Apollo, extract_apollo_state


@dataclass
class ListPage:
    total: int
    codes: list[int]  # 화면 순서 그대로 (광고 카드 제외)


def parse_list_page(html: str) -> ListPage:
    ap = Apollo(extract_apollo_state(html))
    root = ap.get("ROOT_QUERY") or {}
    page = Apollo.field(root, "spots(")
    if not page:
        return ListPage(total=0, codes=[])
    codes = [int(s["code"]) for s in ap.deref_list(page.get("edges")) if "code" in s]
    return ListPage(total=int(page.get("totalCount") or 0), codes=codes)
