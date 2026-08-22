# HOSU Heat Copilot — 기술 스펙

> 기준일: 2026-08-22. 여러 API를 병렬로 탐색하면서 정보가 흩어졌던 걸 이 문서 하나로 모음.
> **이번 정리에서 JUSO 좌표제공 API와 safemap.go.kr 무더위쉼터는 스코프 밖으로 뺐다** — 승인을
> 못 받아서 지금 단계의 고려사항이 아니다(§5-F). 이후 작업은 이 문서를 기준으로 진행한다.

## 1. 개요

JunctionX Korea 2026 경북 트랙, 팀 HOSU. 폭염대응 현장인력(주민생명 지킴이 등)에게 "오늘 어느
마을부터 확인할지" 우선순위를 판정해주는 도구. 대시보드가 아니라 판정형(verdict) UX — 정보
나열이 아니라 답을 낸다. 위험도(HVI: 노출×민감도×적응능력)는 AI가 아니라 명시적 수식으로
계산하고, AI는 요약·자연어 변환에만 쓴다(재현성·감사가능성 확보).

**대상 범위: 경상북도만.**

## 2. 아키텍처 (6단)

1. 공공데이터 API (기상청, 한국사회보장정보원 등)
2. 데이터 파이프라인(Python) — 좌표 정규화·위험도 스코어링
3. 정규화 데이터 스토어(SQLite)
4. MCP 서버(Python) — `mcp_server.py`
5. AI 에이전트(Claude API) ↔ 대시보드 백엔드(FastAPI, 미착수)
6. 프론트엔드(React, 판정 UI, 미착수)

서버(MCP·백엔드)는 **로컬 호스팅으로 확정**. 발표가 팀이 직접 노트북으로 데모하는 방식이라
클라우드 배포는 하지 않는다.

## 3. 지역 필터링 — 서로 다른 두 코드 체계

같은 경상북도를 가리키는 값이라도 API마다 코드 체계가 달라서, 필터링 함수를 코드 체계별로
분리했다(`pipeline/db.py`). 하나로 억지로 합치지 않는다.

| 함수 | 대상 | 판정 규칙 | 근거 |
|---|---|---|---|
| `is_target_region(code)` | emd_code, sigungu_code, jrsdSggCd (법정동코드 계열) | `47`로 시작 | 대구(`27`)는 별도 시도코드라 자동 제외 |
| `is_target_alert_zone(code)` | 기상청 API허브 REG_ID/REG_UP | `L107`로 시작 | 실호출로 확인: 경북 산하 전부 `L107x`, 대구는 `L114`로 완전 분리 |

`require_target_region(code)`는 `is_target_region`이 실패하면 빈 결과 대신 `ValueError`를
던진다 — MCP tool이 범위 밖 조회를 "데이터 없음"으로 오인하지 않게 하기 위함.

## 4. 데이터 스키마 (`pipeline/db.py`)

중심 허브 `ADMIN_REGION`(emd_code PK)에 아래가 FK로 연결. 격자(grid_nx/ny)와 특보구역
(alert_zone_code)은 서로 다른 좌표계라 각자 컬럼으로 분리 보관 — 하나로 근사 매핑하지 않는다.

```
ADMIN_REGION(emd_code PK, sido_name, sigungu_name, emd_name,
             grid_nx, grid_ny,        -- 기상청 5km 격자 (초단기실황용)
             alert_zone_code,         -- 기상청 API허브 특보구역코드 REG_ID (특보용)
             center_lat, center_lon)

WEATHER_ALERT(grid_nx, grid_ny, announce_time, alert_type, temperature, feels_like, humidity)
  PK (grid_nx, grid_ny, announce_time)

WEATHER_WARNING(alert_zone_code, announce_time, tm_seq, title, alert_type)
  PK (alert_zone_code, announce_time, tm_seq)
  -- WEATHER_ALERT와 별도 테이블. 한 PK에 격자 기준 행과 특보구역 기준 행을 섞으면
  -- HEAT_ILLNESS에서 겪은 NULL-in-PK 버그가 재발하기 때문.

HEAT_ILLNESS(sigungu_code, occur_date, age_group, patient_count, is_death)
  PK (sigungu_code, occur_date, age_group) — 전부 NOT NULL
  -- 온열질환은 (지역,날짜,연령대)별 집계라 age_group이 PK 밖이면 같은 날 여러 연령대가
  -- 못 들어가는 버그가 있었음(수정됨).

ELDERLY_ALONE(sigungu_code, year, age_65_69~85_over)  PK (sigungu_code, year)
SAFETY_TARGET(target_id PK, emd_code FK, target_count)
HEAT_SHELTER(shelter_id PK, emd_code FK, name, lat, lon, capacity, has_aircon)

WELFARE_FACILITY(facility_id PK, emd_code FK, name, facility_type, address, lat, lon)
  -- address는 원 ER 설계엔 없던 컬럼. 소스 API가 emd_code/좌표 없이 주소 텍스트만 줘서
  -- 지오코딩 전까지 원본을 보관해두려고 추가함(§5-F, 지금은 스코프 밖).

EMERGENCY_HOSPITAL(hospital_id PK, emd_code FK, name, lat, lon, available_beds)
RISK_SCORE(emd_code FK, score_date, exposure_score, sensitivity_score, access_score,
           total_score, priority_tier, nearest_shelter_id FK→HEAT_SHELTER)
  PK (emd_code, score_date)
```

## 5. 데이터 소스 현황 (재점검, 2026-08-22)

### A. 연동 완료 — 코드 있음, 실호출 검증됨

| 소스 | 파일 | 채워지는 컬럼 | 비어있는 컬럼 |
|---|---|---|---|
| 기상청 초단기실황(`getUltraSrtNcst`, data.go.kr) | `pipeline/sources/weather.py` | `WEATHER_ALERT.temperature`, `.humidity` | `alert_type`(§B), `feels_like`(§E) |
| 한국사회보장정보원 사회복지시설(`getFcltByBassInfoInqire`, data.go.kr) | `pipeline/sources/welfare_facility.py` | `WELFARE_FACILITY.facility_id/name/facility_type/address` | `emd_code`/`lat`/`lon`(§F, 지오코딩 필요 — 스코프 밖) |

두 소스 다 `DATA_GO_KR_SERVICE_KEY` 재사용(추가 신청 불필요). `unquote()` 처리 필요(인증키
Encoding 버전 이중인코딩 방지) — `_service_key()` 헬퍼로 각 파일에 구현돼 있음(현재 소스가
2개뿐이라 공용 모듈로 아직 안 뽑음).

### B. API 확정·검증 완료, 소스 모듈 구현 대기

| 소스 | 오퍼레이션 | 상태 |
|---|---|---|
| 기상청 API허브 특보현황조회(`wrn_now_data.php`) | apihub.kma.go.kr | 신청 즉시 승인, 실호출로 경북 실데이터(고령군·칠곡군 폭염경보 등) 확인함. `WRN`/`LVL`이 코드로 구조화돼 있어 텍스트 파싱 불필요. 응답이 **EUC-KR 인코딩**이라 `response.encoding = 'euc-kr'` 필요 |

data.go.kr의 옛 기상특보 API(`getWthrWrnList`/`getPwnStatus`, stnId 기반)는 격자와 안 맞고
자유텍스트뿐이라 **폐기** — 위 API허브 버전으로 교체 확정.

다음 단계에서 `pipeline/sources/weather_warning.py` 작성 예정: `authKey` 하드코드 대신
`.env`의 `KMA_APIHUB_KEY`로 분리, `REG_UP`으로 `is_target_alert_zone` 필터, `WEATHER_WARNING`
에 적재.

### C. 신청함, 승인 대기중 (data.go.kr)

- 보건복지부 응급안전안심 서비스 대상자 기본정보 → `SAFETY_TARGET`
- 보건복지부 독거노인 수 → `ELDERLY_ALONE`

### D. 승인됐지만 우선순위상 보류

- 국립중앙의료원 응급의료기관 → `EMERGENCY_HOSPITAL` (의도적으로 뒤로 미룸, 재개 시점 미정)

### E. 승인됐지만 필드 미조사

- 기상청 생활기상지수(4.0) — `feels_like` 채울 후보
- 질병관리청 온열질환 감시데이터(파일데이터, REST 아님) — `HEAT_ILLNESS` 채울 후보

### F. 스코프 제외 (이번 정리에서 고려하지 않음 — 승인 못 받음)

- **JUSO_API_KEY**(juso.go.kr 좌표제공 검색 API) — 신청함, 승인 대기. `WELFARE_FACILITY`의
  `emd_code`/`lat`/`lon`, `geocode_address()` 완성이 여기 막혀있음.
- **safemap.go.kr 무더위쉼터**(`IF_0001`) — 키는 있는데 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR`
  지속, 원인 불명. `HEAT_SHELTER` 테이블 통째로 빈 상태.

## 6. 코드 구조

```
pipeline/
  db.py                    스키마 DDL + 지역 필터(§3)
  geo.py                   좌표 변환(pyproj), KMA 격자 변환, ADMIN_REGION 지연 upsert,
                           geocode_address() — §F 대기로 미완성(NotImplementedError)
  sources/
    weather.py             §A - 초단기실황
    welfare_facility.py    §A - 사회복지시설
    (weather_warning.py)   §B - 다음 단계에서 작성
mcp_server.py              MCP tool 4개 (아래 §7 제약 참고)
test_*.py / sources/test_*.py   각 모듈 자체 점검 (5세트, 전부 통과 확인함)
```

## 7. 알려진 제약 (다음 사람이 헷갈리기 쉬운 것)

- **`get_welfare_facilities(emd_code)`가 지금은 사실상 항상 빈 배열을 준다** — 적재된
  `WELFARE_FACILITY` 행 전부 `emd_code IS NULL`(§F, 지오코딩 대기)이라 `WHERE emd_code = ?`
  조건에 아무것도 안 걸림. 코드 버그 아님, §F가 풀리기 전까지의 당연한 상태.
- `WEATHER_ALERT.alert_type`/`.feels_like`는 여전히 전부 NULL — §B/§E가 붙어야 채워짐.
- `ADMIN_REGION`은 아직 안동시(§A 라이브 테스트로 들어간 것) 정도만 있고, 경북 23개 시군
  전체를 커버하는 레지스트리는 없음 — 각 소스가 실제로 다루는 지역만 그때그때 채워짐(지연
  upsert 패턴, `upsert_admin_region`).

## 8. 다음 단계 (우선순위)

1. `pipeline/sources/weather_warning.py` 작성 (§B, 막힌 것 없음 — 바로 가능)
2. §C 승인 나오면 해당 소스 착수
3. §F(JUSO/safemap) 승인 나오면 재검토 — 그 전까지는 이 문서에서도 더 안 건드림
