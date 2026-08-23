# HOSU — 경북 폭염 위험도 데이터 인프라

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**JunctionX Korea 2026 · 마이크로소프트 코리아 트랙 (경상북도 현안 해결)**

경상북도 폭염 대응 공공데이터를 하나의 행정코드·좌표계로 정규화하고,
AI가 즉시 호출할 수 있는 **MCP(Model Context Protocol) 서버**로 공개하는 오픈 데이터 인프라입니다.
그 위에 경북 폭염TF가 실제로 쓰는 **의사결정 대시보드**를 얹었습니다.

```
경북 읍·면·동 383곳 + 시군구 23곳   |   무더위쉼터 5,605개소   |   MCP Tool 8종
```

---

## 빠른 시작 (3분)

```bash
git clone <이 저장소>
cd JHosu/song

pip install -r requirements.txt
cp .env.example .env          # API 키 없이도 전부 동작합니다

python 1_data_infrastructure/pipeline/build.py    # 공공데이터 → 정규화 DB
python 2_regional_service/app.py                  # http://localhost:5050
```

API 키가 없어도 됩니다 — 정규화된 공공데이터 CSV가 저장소에 포함돼 있습니다.

---

## 저장소 구성

트랙이 제시한 두 갈래(**데이터 인프라 구축** / **지역 문제해결 서비스**)를
레이어로 분리해 둘 다 구현했습니다.

```
song/
├── 1_data_infrastructure/     [Layer 1] 공공데이터 정규화 & MCP 서버
│   ├── pipeline/build.py      좌표계 통일 → 행정코드 결합 → 위험도 스코어링
│   ├── mcp_server/server.py   AI가 호출하는 MCP Tool 8종
│   └── data/                  정규화 SQLite DB + 원천 공공데이터 CSV 6종
│
└── 2_regional_service/        [Layer 2] 경북 폭염TF 현안 해결 서비스
    ├── app.py                 대시보드 백엔드
    ├── briefing.py            AI 상황 브리핑 — "오늘 어디부터 가라"
    └── static/index.html      인터랙티브 지도 & 사각지대 시각화
```

무거운 가공은 파이프라인이 미리 끝내고, 서버는 조회만 합니다.
그래서 AI 클라이언트와 웹 대시보드가 **같은 데이터·같은 판단 근거**를 공유합니다.

## 무엇을 답할 수 있나

MCP 서버를 Claude Desktop 등에 연결하면 자연어로 바로 질의할 수 있습니다.

> "오늘 경북에서 가장 먼저 확인해야 할 읍·면 5곳은?"
> "의성군 위험도가 왜 높아?"
> "위험도는 높은데 담당 인력이 안 붙은 지역 알려줘"

점수만 던지지 않고 **왜 그 점수인지 근거를 함께 반환**합니다.
담당 공무원이 검증할 수 없는 판단은 현장에서 쓰이지 않기 때문입니다.

## 자세한 문서

- [song/README.md](song/README.md) — 아키텍처, Tool 명세, 위험도 산출 방식, 데이터 출처
- [song/1_data_infrastructure/README.md](song/1_data_infrastructure/README.md) — 데이터 인프라 상세
- [song/2_regional_service/README.md](song/2_regional_service/README.md) — 대시보드 상세

## 라이선스

[MIT License](LICENSE) — 원본 공공데이터는 각 제공기관의 이용조건을 따릅니다.
