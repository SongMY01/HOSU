"""Self-check for pipeline/sources/weather.py. Run: python -m pipeline.sources.test_weather"""

from datetime import datetime

from pipeline.db import get_conn
from pipeline.sources import weather
from pipeline.sources.weather import _freshness_cutoff, load, normalize, refresh_all

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


def test_normalize_rejects_kma_missing_sentinel():
    """격자 범위 밖이면 기상청은 에러가 아니라 -999/-998을 HTTP 200으로 준다(실호출 확인).
    그대로 저장하면 기온 -999도가 위험도 계산에 들어간다 — NULL로 떨어뜨려야 한다."""
    missing = [
        {"baseDate": "20260823", "baseTime": "0100", "category": "T1H", "nx": 122, "ny": 85, "obsrValue": "-999"},
        {"baseDate": "20260823", "baseTime": "0100", "category": "REH", "nx": 122, "ny": 85, "obsrValue": "-998"},
    ]
    row = normalize(missing)
    assert row["temperature"] is None, row
    assert row["humidity"] is None, row
    # 정상값은 그대로 살아있어야 한다(임계값이 실제 기온을 잡아먹으면 안 됨)
    assert normalize(SAMPLE_ITEMS)["temperature"] == 23.6


def test_freshness_cutoff_gives_one_hour_of_slack():
    """기준시각 정각 비교면 기상청 발표 지연 시 캐시가 영원히 안 맞는다 — 한 시간 여유 확인."""
    # 14:50 → 기준시각 14:00(40분 넘었으므로) → 컷오프는 그 한 시간 전
    assert _freshness_cutoff(datetime(2026, 8, 23, 14, 50)) == "20260823T13:00"
    # 14:10 → 아직 14시 값 미발표 → 기준시각 13:00 → 컷오프 12:00
    assert _freshness_cutoff(datetime(2026, 8, 23, 14, 10)) == "20260823T12:00"


def _seed_grids(conn, grids):
    for i, (nx, ny) in enumerate(grids):
        conn.execute(
            "INSERT INTO ADMIN_REGION (emd_code, grid_nx, grid_ny) VALUES (?, ?, ?)",
            (f"4717{i:05d}", nx, ny),
        )
    conn.commit()


def _stub_fetch(calls, fail_on=()):
    """fetch_current_conditions를 대체 — 네트워크 없이 호출된 격자를 기록한다."""

    def fake(nx, ny):
        calls.append((nx, ny))
        if (nx, ny) in fail_on:
            raise RuntimeError("boom")
        base = datetime.now().strftime("%Y%m%d %H00").split()
        return [
            {"baseDate": base[0], "baseTime": base[1], "category": "T1H", "nx": nx, "ny": ny, "obsrValue": "30.0"},
            {"baseDate": base[0], "baseTime": base[1], "category": "REH", "nx": nx, "ny": ny, "obsrValue": "60"},
        ]

    return fake


def test_refresh_all_skips_grids_already_fresh():
    """캐시 = WEATHER_ALERT 자체. 이번 시각 행이 있으면 네트워크 호출이 아예 안 나가야 한다."""
    conn = get_conn(":memory:")
    _seed_grids(conn, [(91, 106), (92, 107)])
    now_ann = datetime.now().strftime("%Y%m%dT%H:00")
    conn.execute(
        "INSERT INTO WEATHER_ALERT (grid_nx, grid_ny, announce_time, temperature) VALUES (91, 106, ?, 25.0)",
        (now_ann,),
    )
    conn.commit()

    calls = []
    original, weather.fetch_current_conditions = weather.fetch_current_conditions, _stub_fetch(calls)
    try:
        result = refresh_all(conn)
    finally:
        weather.fetch_current_conditions = original

    assert calls == [(92, 107)], calls  # 91,106은 캐시 적중이라 호출 안 됨
    assert result["cached"] == 1 and result["loaded"] == 1, result


def test_refresh_all_survives_one_bad_grid():
    """격자 하나가 죽어도 나머지는 적재돼야 한다 — 302개 중 1개 때문에 전량 손실 방지."""
    conn = get_conn(":memory:")
    _seed_grids(conn, [(91, 106), (92, 107), (93, 108)])

    calls = []
    original, weather.fetch_current_conditions = (
        weather.fetch_current_conditions,
        _stub_fetch(calls, fail_on={(92, 107)}),
    )
    try:
        result = refresh_all(conn)
    finally:
        weather.fetch_current_conditions = original

    assert result["loaded"] == 2 and result["failed"] == 1, result
    stored = conn.execute("SELECT COUNT(*) FROM WEATHER_ALERT").fetchone()[0]
    assert stored == 2, stored


if __name__ == "__main__":
    test_normalize_maps_categories_to_weather_alert_row()
    test_normalize_and_insert_round_trip()
    test_load_skips_non_gyeongbuk_without_network_call()
    test_normalize_rejects_kma_missing_sentinel()
    test_freshness_cutoff_gives_one_hour_of_slack()
    test_refresh_all_skips_grids_already_fresh()
    test_refresh_all_survives_one_bad_grid()
    print("OK: weather.py self-check passed")
