# HOSU — 경북 폭염 위험도 데이터 인프라

JunctionX Korea 2026 · 마이크로소프트 코리아 트랙 (경상북도 현안 해결)

경상북도 폭염 대응 공공데이터를 정규화·결합해, AI가 즉시 호출할 수 있는
MCP 서버 형태로 공개하는 오픈 데이터 인프라입니다.

## 왜 만들었나

경북도 폭염TF는 7개 유형 대상에 1만 명 이상의 인력과 788억 원을 이미 배치했습니다.
그러나 각 채널(생활지원사·주민생명 지킴이·예방요원)의 오늘자 데이터를
한 화면에서 비교해 **"오늘 어디에 자원을 더 투입해야 하는지"** 판단할 도구가 없습니다.

HOSU는 흩어진 공공데이터를 하나의 좌표계·행정코드 기준으로 묶어
그 판단 근거를 제공합니다.

## 프로젝트 레이어 구조

본 프로젝트는 **JunctionX Korea 2026 해커톤 트랙**의 두 가지 핵심 축을 명확히 분리하여 구현했습니다.

```
song/
├── 1_data_infrastructure/        # [Layer 1] 공공데이터 정규화 & MCP 서버 인프라
│   ├── pipeline/                 # 데이터 정규화 및 스코어링 배치 (build.py)
│   ├── mcp_server/               # AI 연동 표준 FastMCP 서버 (server.py)
│   └── data/                     # 정규화 SQLite DB (hosu.db) 및 원천 CSV (6종)
│
└── 2_regional_service/           # [Layer 2] 경북 폭염TF 현안 해결 서비스
    ├── app.py                    # 대시보드 백엔드 서버
    └── static/index.html         # 인터랙티브 지도 & 사각지대 시각화 UI
```

---

## 빠른 시작 (5분)

```bash
cd song
pip install -r requirements.txt

# 1. [Layer 1] 데이터 파이프라인 빌드 및 MCP 서버 검증
python 1_data_infrastructure/pipeline/build.py         # 정규화 + 스코어링 -> data/hosu.db
python 1_data_infrastructure/mcp_server/smoke_test.py  # MCP Tool 동작 검증
python 1_data_infrastructure/mcp_server/server.py      # MCP 서버 실행

# 2. [Layer 2] 현안 해결 웹 대시보드 실행
python 2_regional_service/app.py                       # http://localhost:5050 접속
```

Claude Desktop 등 MCP 클라이언트에 연결하려면 `1_data_infrastructure/mcp_server/mcp.json` 참고.

---

## 아키텍처

```
[ 공공데이터 소스 ]
  기상청(초단기실황) / 통계청(인구) / 행안부(쉼터) / 질병관리청(온열질환)
        │
        ▼
========================================================================
[ Layer 1: Data Infrastructure ]  (1_data_infrastructure/)
  ├── pipeline/build.py  ← 좌표계 통일(위경도→격자), 행정코드 결합, 스코어링
  ├── data/hosu.db       ← 정규화된 읽기 전용 저장소
  └── mcp_server/        ← FastMCP 기반 AI 표준 Tool 노출 (server.py)
========================================================================
        │
        ├───────────────────────────────────┐
        ▼                                   ▼
[ AI 클라이언트 / LLM 에이전트 ]    [ Layer 2: Regional Service ]
  Claude Desktop, LangChain 등       (2_regional_service/app.py)
  (자연어 기반 위험도/사각지대 질의)    (경북 폭염TF 상황판 & 현장 대응 UI)
```

핵심은 **무거운 가공은 파이프라인이 미리, 서버는 조회만** 한다는 분리입니다.

## 제공 Tool (Layer 1 MCP Server)

| Tool | 설명 |
|---|---|
| `get_heat_risk_score(region)` | 지역의 오늘자 위험도 점수 + 판단 근거 |
| `list_high_priority_regions(top_n, level)` | 우선대응 지역 순위 |
| `get_shelter_coverage(region)` | 무더위쉼터 도보권 접근성, 사각지대 여부 |
| `get_vulnerable_population(region)` | 고령·농업인·독거노인 집계 지표 |
| `find_uncovered_regions(min_risk)` | 위험도는 높은데 어떤 채널도 닿지 않는 지역 |

### 응답 예시

```json
{
  "region_name": "의성군",
  "risk_score": 55.9,
  "risk_grade": "높음",
  "realtime": { "feels_like_c": 31.5, "level": "주의" },
  "reasons": [
    "고령인구 비율 52.3%로 높음",
    "농업인 비율 52.6%로 야외노출 많음",
    "도보 5분권 무더위쉼터 없음 (최근접 1700m)"
  ]
}
```

블랙박스 점수가 아니라 **왜 그 점수인지 근거를 함께 반환**합니다.
담당 공무원이 납득할 수 없는 판단은 현장에서 쓰이지 않기 때문입니다.

## 위험도 산출 방식

```
최종 위험도 = 정적 기저 위험도 × 0.6 + 실시간 체감온도 위험도 × 0.4

정적 기저 = 고령인구 0.35 + 농업인 0.25 + 쉼터접근성 0.25 + 과거이력 0.15
```

- 가중치는 `pipeline/build.py`의 `WEIGHTS`에서 조정 가능
- 머신러닝 대신 **설명 가능한 가중치 모델**을 택했습니다.
  현장 담당자가 근거를 검증하고 지역 특성에 맞게 조정할 수 있어야 하기 때문입니다.
- 쉼터 사각지대 판정 기준 400m(도보 5분)는 국립재난안전연구원 분석 기준을 차용했습니다.

## 데이터 출처

| 데이터 | 출처 | 갱신 주기 |
|---|---|---|
| 체감온도 실황 | 기상청 초단기실황 API | 실시간 (10분 캐시) |
| 온열질환 발생 | 질병관리청 온열질환 감시체계 | 일 1회 |
| 무더위쉼터 | 공공데이터포털 전국무더위쉼터표준데이터 | 주 1회 |
| 고령·농업인 인구 | 통계청 KOSIS, 주민등록 인구통계 | 연 1회 |
| 행정구역 경계 | 행정표준코드, SGIS 경계 | 연 1회 |

### 실데이터 연결

`pipeline/build.py`의 `load_*()` 함수가 어댑터입니다.
샘플 CSV 대신 실제 API를 호출하도록 이 함수들만 교체하면 됩니다.

기상청 API는 환경변수로 키를 넣으면 자동 연결됩니다.

```bash
export KMA_API_KEY="발급받은_인증키"
```

키가 없으면 격자별 결정론적 폴백값을 반환해 개발·데모가 끊기지 않습니다.

## 개인정보 관련

모든 데이터는 **행정구역 단위 집계값**입니다.
개인 식별정보, 주소, 연락처는 수집·저장·반환하지 않습니다.
`channel_coverage` 테이블의 채널 배정 현황은 지자체 내부 데이터이므로
현재는 시뮬레이션 값이며, 실제 도입 시 기관 데이터로 교체해야 합니다.

## 프로젝트 구조

```
hosu/
├── pipeline/
│   ├── build.py          배치 파이프라인 (수집→정규화→스코어링→DB)
│   └── seed_sample.py    샘플 원본 데이터 생성기
├── mcp_server/
│   ├── server.py         MCP 서버 (Tool 정의)
│   ├── weather.py        기상청 실시간 어댑터
│   └── smoke_test.py     Tool 동작 검증
├── schema/
│   └── schema.sql        DB 스키마 (파이프라인·서버 공통 계약)
└── data/
    ├── raw/              원본 CSV
    └── hosu.db           파이프라인 산출물
```

## 확장

행정구역 코드 기준으로 설계했기 때문에, `data/raw/`의 원본 데이터만 교체하면
다른 시도(대구·전남 등)에도 그대로 적용됩니다.
폭염 외 한파·미세먼지 등 다른 재난 지표로도 스코어링 축을 바꿔 재사용할 수 있습니다.

## 라이선스

MIT License
