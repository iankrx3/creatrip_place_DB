# creatrip 장소 DB

온보딩 추천(FIX skin/face, 다운타임, CHANGE/RESTORE, 여행 기간, 지역, 예산, 언어, 루틴 시간표, 점수)에 필요한 장소 정보를
creatrip.com 에서 Selenium 으로 수집해 `data/places.json` / `data/places.csv` 로 관리한다.
외부 API(LLM, 지오코딩 등)는 쓰지 않는다. 페이지에 있는 정보와 `config/` 의 규칙·사전만 사용한다.

## 실행

```bash
pip install -r requirements.txt
python -m scraper                                        # 카테고리마다 새 장소 10곳 추가
python -m scraper --categories dermatology,sauna --per-category 3
python -m scraper --refresh --categories massage         # 저장된 장소를 다시 수집
python -m normalize.build --from-raw                     # 규칙 수정 후 data/raw 스냅샷으로 재정규화
pytest -q                                                # 저장된 페이지 스냅샷으로 파서 테스트 (네트워크 없음)
```

GitHub Actions (`.github/workflows/scrape.yml`)는 매일 03:00 KST 에 실행되고, `data/` 변경분을 PR 로 올린다.
수동 실행(workflow_dispatch)에서 `categories`, `per_category`, `refresh` 를 지정할 수 있다.
PR 을 만들려면 저장소 Settings → Actions → General → "Allow GitHub Actions to create and approve pull requests" 를 켜야 한다.

## 수집 방식

| 단계 | 내용 |
|---|---|
| 목록 | `config/categories.yaml` 의 카테고리마다 조회수 순 목록을 넘기며 **아직 저장되지 않은** 장소를 `per_category`(기본 10)개 고른다. 이미 저장된 장소가 다른 카테고리 목록에 나오면 `extra_subtypes` 에만 추가한다. |
| 상세 | 페이지를 열고 접힌 옵션 그룹("Select Options")을 펼친 뒤, 페이지에 포함된 `__NEXT_DATA__`(좌표·영업시간·가격·평점·카테고리·언어 Remark)와 화면 텍스트(하위 옵션, 유의사항, Available Languages)를 함께 저장한다. |
| 정규화 | `normalize/place.py` 가 스냅샷을 `Place` 스키마(`normalize/schema.py`)로 바꾼다. |
| 예의 | 요청 사이 1~3초 랜덤 대기, 동시 1개, 실패하면 백오프 후 3회 재시도, 계속 실패한 장소는 `data/failed.json` 에 남겨 다음 실행에서 먼저 재시도. |

CloudFront 가 `HeadlessChrome` User-Agent 를 403 으로 막기 때문에 `scraper/driver.py` 에서 UA 의 브라우저 이름만 `Chrome` 으로 바꾼다.

## 필드와 출처

| 온보딩 | 필드 | 출처 |
|---|---|---|
| FIX / CHANGE / RESTORE | `subtype`, `extra_subtypes`, `onboarding`, `category_path` | 수집한 목록 카테고리 + 페이지 카테고리 |
| FIX skin/face | `procedures[].target`, `fix_targets` | 옵션명 → `config/procedures.yaml` 키워드 매칭 |
| 다운타임 / 여행 기간 | `procedures[].downtime_grade`, `downtime_days_min/max`, `downtime_source`, `downtime_days_max`, `needs_before` | 페이지 문장에 일수/“no downtime” 이 있으면 `page`, 없으면 사전 값 `dictionary` |
| 도시 / 지역 | `city`, `region`, `lat`, `lng`, `address`, `nearest_station` | `__NEXT_DATA__` |
| 예산 | `price_type`, `price_min_usd`, `deposit_usd`, `options[]` | 옵션별 판매가(USD). 예약금만 있는 곳은 `price_min_usd = null` |
| 언어 | `languages[]{code, source, level}` | Available Languages / 예약 Remark = `listed`, 본문 언급 = `mentioned` |
| 루틴 시간표 | `duration_min`, `hours`, `closed_days` | 옵션명의 “(60 minutes)” 등, 요일별 영업시간 |
| 점수 | `rating`, `review_count`, `view_count` | `__NEXT_DATA__` |

페이지에서 확인되지 않는 값은 `null` 로 두고 추측하지 않는다. `missing_fields` 에 비어 있는 핵심 필드가 기록된다.
필드별 채움 현황은 `data/coverage.md` 에서 볼 수 있다.

## 사이트가 바뀌었을 때

- URL·화면 문구·XPath: `scraper/page_spec.py`
- 텍스트 해석 규칙(가격, 소요시간, 하위 옵션, 언어): `normalize/text_rules.py`
- 시술 사전(키워드 → 대상·다운타임): `config/procedures.yaml`
- `tests/fixtures/` 의 스냅샷을 새 페이지로 교체하고 `pytest` 로 확인
