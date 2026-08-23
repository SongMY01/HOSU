# HOSU — 경북 폭염 위험도 데이터 인프라 & 대시보드

JunctionX Korea 2026 · 마이크로소프트 코리아 트랙 (경상북도 현안 해결)

경상북도 폭염 대응 공공데이터를 정규화·결합해, AI가 즉시 호출할 수 있는
표준 MCP 서버(Layer 1) 및 실시간 행정 대시보드(Layer 2)로 제공하는 오픈 솔루션입니다.

---

## 🔗 서비스 링크

- **🌐 웹 대시보드 (Vercel)**: [https://hosu-dashboard.vercel.app](https://hosu-dashboard.vercel.app)
- **⚙️ 백엔드 API & Remote MCP (Railway)**: [https://hosu-backend-production.up.railway.app](https://hosu-backend-production.up.railway.app)
- **📡 Remote MCP SSE Endpoint**: `https://hosu-backend-production.up.railway.app/sse`

---

## 🏛️ 프로젝트 아키텍처

```
HOSU/
├── 1_data_infrastructure/        # [Layer 1] 공공데이터 정규화 & MCP 서버 인프라
│   ├── data/                     # 정규화 SQLite DB (hosu.db) 및 원천 CSV (6종)
│   ├── pipeline/                 # 데이터 정규화 및 스코어링 배치 (build.py, schema.sql)
│   └── mcp_server/               # AI 연동 표준 FastMCP 서버 (server.py, weather.py)
│
├── 2_regional_service/           # [Layer 2] 경북 폭염TF 현안 해결 서비스
│   ├── app.py                    # Flask REST API 백엔드
│   ├── briefing.py               # AI 상황 브리핑 생성
│   ├── frontend/                 # Vite + React 18 SPA 대시보드
│   └── static/                   # React 빌드 결과물
│
├── asgi.py                       # 통합 ASGI 서버 (Flask API + Remote MCP SSE)
├── Dockerfile                    # Railway 클라우드 배포용 Docker 설정
├── requirements.txt              # 전체 Python 의존성 목록
└── README.md
```

---

## 🚀 빠른 시작

### 1. 의존성 설치
```bash
pip install -r requirements.txt
```

### 2. 데이터 파이프라인 빌드 & 테스트
```bash
python 1_data_infrastructure/pipeline/build.py         # 공공데이터 정규화 -> data/hosu.db
pytest 1_data_infrastructure/pipeline/test_build.py    # 스코어링 회귀 테스트
```

### 3. 로컬 서버 실행
```bash
# 통합 서버 (Flask REST + Remote MCP SSE)
uvicorn asgi:app --port 5050 --reload

# 또는 React 프론트엔드 개발 서버
cd 2_regional_service/frontend && npm run dev
```

---

## 🤖 AI 에이전트 연동 (Claude Desktop / Cursor)

### 방법 1: 원격 URL 연동 (설치 불필요 ⭐)
Claude Desktop 설정(`claude_desktop_config.json`)에 아래 한 줄만 추가하면 즉시 사용 가능합니다:

```json
{
  "mcpServers": {
    "hosu-heat-risk": {
      "url": "https://hosu-backend-production.up.railway.app/sse"
    }
  }
}
```

### 방법 2: 로컬 파이썬 연동
```json
{
  "mcpServers": {
    "hosu-heat-risk": {
      "command": "python",
      "args": [
        "/절대경로/HOSU/1_data_infrastructure/mcp_server/server.py"
      ],
      "env": {
        "PYTHONPATH": "/절대경로/HOSU/1_data_infrastructure:/절대경로/HOSU/1_data_infrastructure/mcp_server"
      }
    }
  }
}
```

---

## 🛠️ 제공 MCP Tool 목록 (7종)

| Tool | 설명 |
|---|---|
| `get_heat_risk_score(region)` | 특정 읍면동의 종합 폭염 위험도 점수 및 산출 근거 반환 |
| `get_current_weather(region)` | 특정 지역의 실시간 기상 실측치(기온·습도·체감온도·위험단계) 조회 |
| `list_high_priority_regions(top_n, level)` | 오늘 우선 대응이 필요한 위험 지역 TOP N 추출 |
| `check_shelter_accessibility(region)` | 도보 5분권(400m) 내 무더위쉼터 접근성 및 사각지대 판별 |
| `find_shelter_blind_spots(level)` | 관내 쉼터가 부족한 취약지역 목록 추출 |
| `get_region_shelters(region, limit)` | 관내 등록된 무더위쉼터 위치, 수용인원, 냉방기기 스펙 목록 |
| `explain_risk_calculation(region)` | 위험도 산출 공식(고령인구·쉼터접근성·온열질환이력·실시간기온) 및 가중치 설명 |
