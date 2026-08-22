"""MCP Tool 로직 검증. MCP 프로토콜 없이 함수를 직접 호출한다.
실행: python mcp_server/smoke_test.py
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import server as S


def show(title, obj):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def unwrap(tool):
    """MCP 데코레이터로 감싸인 함수에서 원본을 꺼낸다."""
    return getattr(tool, "fn", getattr(tool, "__wrapped__", tool))


show("1. 의성군 위험도", unwrap(S.get_heat_risk_score)("의성군"))
show("2. 우선대응 상위 5개 시군", unwrap(S.list_high_priority_regions)(5, "sigungu"))
show("3. 청송군 쉼터 접근성", unwrap(S.get_shelter_coverage)("청송군"))
show("4. 영양군 취약인구", unwrap(S.get_vulnerable_population)("영양군"))
show("5. 포항시 구룡포읍 인근 쉼터 위치 (반경 1.5km)", unwrap(S.get_nearby_shelters)("포항시 구룡포읍", radius_m=1500, limit=3))
show("6. '행정복지센터' 쉼터 검색 (안동시)", unwrap(S.search_shelters)("행정복지센터", sigungu="안동시", limit=3))
show("7. 경산시 압량읍 실시간 기상 실측 (gyeongbuk_weather.csv)", unwrap(S.get_current_weather)("경산시 압량읍"))


