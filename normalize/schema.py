"""장소 레코드 스키마. 페이지에서 확인되지 않은 값은 None 으로 둔다 (추측하지 않는다)."""

from typing import Literal

from pydantic import BaseModel, Field

DowntimeGrade = Literal["none", "low", "high"]
Source = Literal["page", "dictionary", "subtype_default"]


class Option(BaseModel):
    name: str
    group: str | None = None
    description: str | None = None
    price_usd: float | None = None
    original_price_usd: float | None = None
    price_krw: int | None = None
    duration_min: int | None = None


class Procedure(BaseModel):
    key: str
    target: str
    downtime_grade: DowntimeGrade
    downtime_days_min: int
    downtime_days_max: int
    downtime_source: Source
    matched_options: list[str] = Field(default_factory=list)


class Language(BaseModel):
    code: str
    name: str
    source: Literal["available_languages", "remark", "text"]
    level: Literal["listed", "mentioned"]


class Station(BaseModel):
    name: str
    line: str | None = None
    distance_m: int | None = None


class Place(BaseModel):
    id: int
    url: str
    name: str
    name_ko: str | None = None
    active: bool = True

    # 카테고리 (FIX / CHANGE / RESTORE)
    subtype: str
    extra_subtypes: list[str] = Field(default_factory=list)
    onboarding: str | None = None
    category_path: list[str] = Field(default_factory=list)

    # FIX skin/face, 다운타임, 여행 기간
    procedures: list[Procedure] = Field(default_factory=list)
    fix_targets: list[str] = Field(default_factory=list)
    downtime_grade: DowntimeGrade | None = None
    downtime_days_max: int | None = None
    needs_before: list[str] = Field(default_factory=list)
    downtime_notes: list[str] = Field(default_factory=list)

    # 도시 / 지역
    city: str | None = None
    region: str | None = None
    lat: float | None = None
    lng: float | None = None
    address: str | None = None
    nearest_station: Station | None = None
    telephone: str | None = None

    # 예산
    price_type: Literal["paid", "free_reservation", "deposit", "free"] | None = None
    price_min_usd: float | None = None
    price_krw: int | None = None
    deposit_usd: float | None = None
    options: list[Option] = Field(default_factory=list)

    # 언어
    languages: list[Language] = Field(default_factory=list)

    # 루틴 시간표
    duration_min: int | None = None
    hours: dict[str, list[list[str]]] | None = None
    closed_days: list[str] = Field(default_factory=list)

    # 점수
    rating: float | None = None
    review_count: int | None = None
    view_count: int | None = None

    # 메타
    scraped_at: str
    content_hash: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
