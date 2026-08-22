"""위험도 스코어링 — 명시적 수식만 사용(§1: AI는 요약에만, 판정은 수식으로).

지금은 기온·습도만 실제 데이터라서(SPEC §7 — 온열질환은 시군구 상속, 독거노인 없음),
체감온도 단일 지표로만 스코어링한다. 다른 요인이 붙으면(§C 승인 등) RISK_SCORE의
exposure/sensitivity/access 3축으로 확장 — 지금 미리 그 구조를 만들지 않는다(YAGNI).
"""

import math

# 기상청이 실제 발표에 쓰는 여름철 체감온도 공식(습구온도 경유). 생활기상지수 API
# (§E, 아직 미신청)를 붙이기 전까지 이 수식으로 근사한다 — WEATHER_ALERT.feels_like가
# 왜 계산값인지는 이 함수가 설명한다.
def feels_like_c(temp_c: float, humidity_pct: float) -> float:
    rh = humidity_pct
    tw = (
        temp_c * math.atan(0.151977 * math.sqrt(rh + 8.313659))
        + math.atan(temp_c + rh)
        - math.atan(rh - 1.676331)
        + 0.00391838 * rh**1.5 * math.atan(0.023101 * rh)
        - 4.686035
    )
    return -0.2442 + 0.55399 * tw + 0.45535 * temp_c - 0.0022 * tw**2 + 0.00278 * tw * temp_c + 3.0


# 기상청 폭염특보 발표기준(체감온도 33/35도, 통상 "2일 이상 지속 예상"이 조건이지만 이
# 프로토타입은 한 시점 스냅샷이라 그 지속조건은 뺐다).
# ponytail: 스냅샷 단순화. 연속 이틀 예보 데이터가 붙으면 지속조건을 되살릴 것.
def risk_tier(feels_like: float) -> str:
    if feels_like >= 35:
        return "위험"
    if feels_like >= 33:
        return "주의"
    return "양호"


TIER_COLOR = {"위험": "#dc2626", "주의": "#f59e0b", "양호": "#16a34a"}
