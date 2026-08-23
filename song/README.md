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
    ├── briefing.py               # AI 상황 브리핑 (Claude API)
    └── static/index.html         # 인터랙티브 지도 & 사각지대 시각화 UI
```

> **API 키 의존은 Layer 2에만 있습니다.** Layer 1(데이터 인프라·MCP 서버)은
> 키 없이 완전히 동작하며, AI 브리핑도 키가 없으면 규칙 기반 문장으로 대체됩니다.

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

### AI 클라이언트(Claude Desktop 등)에 연결

`1_data_infrastructure/mcp_server/mcp.json` 의 내용을 클라이언트 설정 파일에 붙여넣고,
`args` 경로만 **클론한 위치의 절대경로**로 바꾸면 됩니다.
MCP 클라이언트는 임의의 작업 디렉토리에서 서버를 실행하므로 상대경로는 동작하지 않습니다.

| 클라이언트 | 설정 파일 위치 |
|---|---|
| Claude Desktop (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Claude Desktop (Windows) | `%APPDATA%\Claude\claude_desktop_config.json` |
| Claude Code | `claude mcp add hosu-heat-risk python3 <절대경로>/server.py` |

연결되면 `"의성군 폭염 위험도 알려줘"`, `"오늘 우선 대응할 읍면동 5곳은?"` 처럼
자연어로 질의할 수 있습니다.

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

`region` 인자는 행정표준코드(`4773025000`)와 지역명(`의성군`, `포항시 구룡포읍`)을 모두 받습니다.

**위험도 판단**

| Tool | 설명 |
|---|---|
| `get_heat_risk_score(region)` | 지역의 오늘자 위험도 점수 + 판단 근거 |
| `list_high_priority_regions(top_n, level)` | 우선대응 지역 순위 (`level`: `sigungu` \| `eupmyeondong`) |
| `find_uncovered_regions(min_risk)` | 위험도는 높은데 어떤 대응 채널도 닿지 않는 지역 |

**현장 대응**

| Tool | 설명 |
|---|---|
| `get_current_weather(region)` | 실시간 기온·습도·체감온도 및 폭염 위험단계 |
| `get_shelter_coverage(region)` | 무더위쉼터 도보권(400m) 접근성, 사각지대 여부 |
| `get_nearby_shelters(region, radius_m, limit)` | 반경 내 쉼터를 거리순으로 — 냉방기기·야간운영·카카오맵 링크 포함 |
| `search_shelters(keyword, sigungu, limit)` | 쉼터명·주소 키워드 검색 |
| `get_vulnerable_population(region)` | 고령(65+/75+/85+)·독거노인·농업인 집계 지표 |

### 응답 예시

```json
{
  "region_name": "의성군",
  "risk_score": 55.9,
  "risk_grade": "높음",
  "realtime": { "feels_like_c": 31.5, "level": "주의" },
  "reasons": [
    "고령인구 비율 52.3%로 높음",
    "도보 5분권 무더위쉼터 없음 (최근접 1700m)"
  ]
}
```

블랙박스 점수가 아니라 **왜 그 점수인지 근거를 함께 반환**합니다.
담당 공무원이 납득할 수 없는 판단은 현장에서 쓰이지 않기 때문입니다.

## 위험도 산출 방식

```
최종 위험도 = 정적 기저 위험도 × 0.6 + 실시간 체감온도 위험도 × 0.4

정적 기저 = 고령인구 0.47 + 쉼터접근성 0.33 + 과거이력 0.20

고령인구 점수 = 65세이상 비율 × (1 ± 초고령 쏠림 보정)
              보정 = (해당지역 85+/65+ 비중 − 경북 평균) / 경북 평균, 최대 ±15%
```

- 폭염 초과사망 위험은 연령이 높을수록 급격히 커지므로, **같은 고령화율이라도
  고령층 내부가 더 고령인 지역을 더 위험하게** 봅니다.
  예: 65세 이상 비율이 51%대로 비슷한 두 지역도 초고령 쏠림에 따라 점수가 갈립니다
  (포항시 남구 대송면 49.2 vs 울진군 평해읍 55.9).
- 65+/75+/85+ 비율을 직접 가중합하지 않은 이유: 세 값이 모두 누적(and-above)이라
  가중합하면 점수 스케일이 구조적으로 내려앉아, 등급·근거 문구 임계값이 무력화됩니다.
  기준선을 유지하는 곱셈 보정 방식을 택했습니다.
- 가중치는 `pipeline/build.py`의 `WEIGHTS`·`ELDERLY_SKEW_MAX_ADJ`에서 조정 가능
- 머신러닝 대신 **설명 가능한 가중치 모델**을 택했습니다.
  현장 담당자가 근거를 검증하고 지역 특성에 맞게 조정할 수 있어야 하기 때문입니다.
- 쉼터 사각지대 판정 기준 400m(도보 5분)는 국립재난안전연구원 분석 기준을 차용했습니다.

## 데이터 출처

| 데이터 | 출처 | 갱신 주기 |
|---|---|---|
| 체감온도 실황 | 기상청 초단기실황 API | 실시간 (10분 캐시) |
| 온열질환 발생 | 질병관리청 온열질환 감시데이터(개인 단위 원본) | 연 1회(계절 종료 후) |
| 무더위쉼터 | 공공데이터포털 전국무더위쉼터표준데이터 | 주 1회 |
| 고령·농업인 인구 | 통계청 KOSIS, 주민등록 인구통계 | 연 1회 |
| 행정구역 경계 | 행정표준코드, SGIS 경계 | 연 1회 |
| ⚠ 채널 커버리지(생활지원사/지킴이 배정) | **시뮬레이션 값** — 지자체 내부 데이터라 공개 출처 없음. 실제 도입 시 기관 데이터로 교체 필요 | - |

### 실데이터 연결

`data/raw/`의 CSV 6종은 모두 **실제 공공데이터를 정규화한 결과물**입니다
(가상 샘플 데이터가 아닙니다). 그래서 API 키 없이 클론만 해도 전체 기능이 동작합니다.

`pipeline/build.py`의 `load_*()` 함수가 어댑터 지점입니다.
CSV 대신 각 기관 API를 주기적으로 호출하도록 이 함수들만 교체하면 운영 파이프라인이 됩니다.
`load_heat_illness()`는 질병관리청 감시데이터 원본(개인 단위)을 직접 집계합니다 —
시군구 단위 원본이라 읍면동 이력 점수는 소속 시군구 값을 상속받습니다.

기상청 실황은 환경변수로 키를 넣으면 자동 연결됩니다.

```bash
cp .env.example .env    # KMA_API_KEY 항목에 발급받은 인증키 입력
```

키가 없으면 포함된 실측 스냅샷(`gyeongbuk_weather.csv`)을 쓰고,
그마저 없는 격자는 결정론적 폴백값으로 대체해 개발·데모가 끊기지 않습니다.

## 개인정보 관련

모든 데이터는 **행정구역 단위 집계값**입니다.
개인 식별정보, 주소, 연락처는 수집·저장·반환하지 않습니다.
`channel_coverage` 테이블의 채널 배정 현황은 지자체 내부 데이터이므로
현재는 시뮬레이션 값이며, 실제 도입 시 기관 데이터로 교체해야 합니다.

## 확장

행정구역 코드 기준으로 설계했기 때문에, `data/raw/`의 원본 데이터만 교체하면
다른 시도(대구·전남 등)에도 그대로 적용됩니다.
폭염 외 한파·미세먼지 등 다른 재난 지표로도 스코어링 축을 바꿔 재사용할 수 있습니다.

## 라이선스

MIT License
