# 🏛️ Layer 1: Data Infrastructure (데이터 인프라 구축)

경상북도 폭염 대응 공공데이터를 수집·정규화·결합하여 AI가 즉시 호출할 수 있는 **MCP (Model Context Protocol) 서버** 및 표준 데이터 인프라를 제공합니다.

---

## 📂 디렉토리 구조

```
1_data_infrastructure/
├── pipeline/                 # [배치 파이프라인] 데이터 정규화 및 스코어링
│   ├── build.py              # 원본 공공데이터 -> 정규화 -> SQLite DB 빌드
│   ├── test_build.py         # 파이프라인 집계 로직 회귀 테스트
│   └── schema.sql            # SQLite 테이블 및 인덱스 DDL 스키마
├── mcp_server/               # [MCP 서버] AI 모델 연동 Tool 엔드포인트
│   ├── server.py             # 8개 폭염 분석 Tool을 제공하는 FastMCP 서버
│   ├── weather.py            # 기상청 초단기실황 API 실시간 체감온도 어댑터
│   ├── smoke_test.py         # MCP 프로토콜 없이 Tool 로직 검증하는 자체 테스트
│   └── mcp.json              # Claude Desktop / AI 클라이언트 연동 설정
└── data/                     # [데이터 저장소] 정규화된 데이터셋
    ├── hosu.db               # 읽기 전용 정규화 SQLite DB
    └── raw/                  # 원천 공공데이터 CSV (5종)
        ├── regions.csv       # 경북 행정구역(시군구 24 + 읍면동 392) 좌표 및 기상청 격자 매핑
        ├── population.csv    # 읍면동 연령별 인구통계 (65+/75+/85+ 초고령 통계)
        ├── shelters.csv      # 무더위쉼터 5,605개소 시설 및 위치 정보
        ├── heat_illness_gyeongbuk.csv # 온열질환 감시 데이터(질병관리청, 개인 단위 원본)
        └── gyeongbuk_weather.csv # 기상청 실시간/실측 기상 데이터
```

---

## 🚀 실행 가이드

### 1. 데이터 파이프라인 빌드 (정규화 및 DB 적재)
```bash
# 원본 데이터를 정규화하고 위험도 DB(data/hosu.db) 생성
python 1_data_infrastructure/pipeline/build.py
```

### 2. MCP Tool 기능 검증
```bash
# Tool 로직 스모크 테스트 실행
python 1_data_infrastructure/mcp_server/smoke_test.py
```

### 3. MCP 서버 실행
```bash
python 1_data_infrastructure/mcp_server/server.py
```

---

## 🛠️ 제공하는 핵심 MCP Tools

모든 `region` 인자는 행정표준코드(`4773025000`)와 지역명(`의성군`, `포항시 구룡포읍`)을 함께 받습니다.

| Tool 명칭 | 설명 | 반환 데이터 |
|---|---|---|
| `get_heat_risk_score(region)` | 특정 지역의 오늘자 폭염 위험도 점수 산출 | 정적 위험도(고령인구/쉼터접근성/발생이력) + 실시간 체감온도 결합 및 산출 근거 |
| `list_high_priority_regions(top_n, level)` | 우선 대응이 필요한 상위 위험 지역 순위 | 시군구/읍면동 단위 상위 N개 지역 목록 및 위험도 |
| `get_current_weather(region)` | 해당 지역의 실시간 기상 실측 | 기온, 습도, 체감온도, 폭염 위험단계, 발표시각, 기상청 격자좌표 |
| `get_shelter_coverage(region)` | 해당 지역의 무더위쉼터 도보권(400m) 접근성 및 사각지대 판정 | 도보 5분 내 쉼터 유무, 최근접 거리(m) |
| `get_nearby_shelters(region, radius_m, limit)` | 반경 내 실제 쉼터를 거리순 조회 | 쉼터명·주소·도보 소요시간·수용인원·냉방기기 대수·야간/휴일 운영·카카오맵 링크 |
| `search_shelters(keyword, sigungu, limit)` | 쉼터명 또는 주소 키워드 검색 | 위와 동일한 쉼터 상세 정보 |
| `get_vulnerable_population(region)` | 고령인구 연령대별 집계 지표 | 총인구, 65세+/75세+/85세+ 인구 및 비율 |
