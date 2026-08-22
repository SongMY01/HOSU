"""Self-check for pipeline/sources/weather.py. Run: python -m pipeline.sources.test_weather"""

from pipeline.db import get_conn
from pipeline.sources.weather import load, normalize

# 2026-08-22 21:00 안동(91,106) 실제 응답(라이브 호출로 확보한 샘플, 재사용)
SAMPLE_ITEMS = [
    {"baseDate": "20260822", "baseTime": "2100", "category": "PTY", "nx": 91, "ny": 106, "obsrValue": "0"},
    {"baseDate": "20260822", "baseTime": "2100", "category": "REH", "nx": 91, "ny": 106, "obsrValue": "91"},
    {"baseDate": "20260822", "baseTime": "2100", "category": "RN1", "nx": 91, "ny": 106, "obsrValue": "0"},
    {"baseDate": "20260822", "baseTime": "2100", "category": "T1H", "nx": 91, "ny": 106, "obsrValue": "23.6"},
    {"baseDate": "20260822", "baseTime": "2100", "category": "UUU", "nx": 91, "ny": 106, "obsrValue": "-1.7"},
    {"baseDate": "20260822", "baseTime": "2100", "category": "VEC", "nx": 91, "ny": 106, "obsrValue": "114"},
    {"baseDate": "20260822", "baseTime": "2100", "category": "VVV", "nx": 91, "ny": 106, "obsrValue": "0.8"},
    {"baseDate": "20260822", "baseTime": "2100", "category": "WSD", "nx": 91, "ny": 106, "obsrValue": "1.9"},
]


def test_normalize_maps_categories_to_weather_alert_row():
    row = normalize(SAMPLE_ITEMS)
    assert row["grid_nx"] == 91 and row["grid_ny"] == 106
    assert row["announce_time"] == "20260822T21:00"
    assert row["temperature"] == 23.6
    assert row["humidity"] == 91.0
    assert row["feels_like"] is None  # 생활기상지수 API 미연결 — 의도적으로 비움
    assert row["alert_type"] is None  # 특보 API 미연결 — 의도적으로 비움


def test_normalize_and_insert_round_trip():
    conn = get_conn(":memory:")
    row = normalize(SAMPLE_ITEMS)
    conn.execute(
        "INSERT INTO WEATHER_ALERT (grid_nx, grid_ny, announce_time, alert_type, temperature, feels_like, humidity) "
        "VALUES (:grid_nx, :grid_ny, :announce_time, :alert_type, :temperature, :feels_like, :humidity)",
        row,
    )
    stored = conn.execute("SELECT temperature, humidity FROM WEATHER_ALERT").fetchone()
    assert stored == (23.6, 91.0), stored


def test_load_skips_non_gyeongbuk_without_network_call():
    """경북 밖이면 upsert_admin_region 단계에서 걸러지고 fetch_current_conditions는 호출 안 됨."""
    conn = get_conn(":memory:")
    # 서울시청 좌표, emd_code가 11(서울)로 시작 — network 호출 없이 False가 나와야 함
    result = load(conn, "11110", lat=37.5665, lon=126.9780)
    assert result is False
    count = conn.execute("SELECT COUNT(*) FROM WEATHER_ALERT").fetchone()[0]
    assert count == 0


if __name__ == "__main__":
    test_normalize_maps_categories_to_weather_alert_row()
    test_normalize_and_insert_round_trip()
    test_load_skips_non_gyeongbuk_without_network_call()
    print("OK: weather.py self-check passed")
