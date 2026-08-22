"""Self-check for scoring.py. Run: python -m pipeline.test_scoring"""

from pipeline.scoring import feels_like_c, risk_tier


def test_feels_like_increases_with_humidity_at_fixed_temp():
    lower = feels_like_c(33.0, 40.0)
    higher = feels_like_c(33.0, 90.0)
    assert higher > lower, (lower, higher)


def test_feels_like_stays_in_sane_range_for_summer_values():
    # 경북 실호출로 관측된 범위(23~37도, 습도 50~95%) 안에서 체감온도가 터무니없이
    # 벗어나지 않는지 — 공식 자체가 깨졌으면 여기서 걸린다.
    for t in (23, 27, 30, 33, 36):
        for rh in (50, 70, 91):
            fl = feels_like_c(t, rh)
            assert t - 5 < fl < t + 10, (t, rh, fl)


def test_risk_tier_thresholds_match_kma_criteria():
    assert risk_tier(32.9) == "양호"
    assert risk_tier(33.0) == "주의"
    assert risk_tier(34.9) == "주의"
    assert risk_tier(35.0) == "위험"


if __name__ == "__main__":
    test_feels_like_increases_with_humidity_at_fixed_temp()
    test_feels_like_stays_in_sane_range_for_summer_values()
    test_risk_tier_thresholds_match_kma_criteria()
    print("OK: scoring.py self-check passed")
