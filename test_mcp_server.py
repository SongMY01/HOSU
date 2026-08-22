"""Self-check for mcp_server.py's query functions. Run: python test_mcp_server.py"""

from pipeline.db import get_conn
from mcp_server import (
    _get_heat_illness_status,
    _get_heatwave_alert,
    _get_welfare_facilities,
    get_heat_illness_status,
    get_heatwave_alert,
    get_welfare_facilities,
)

EMD = "47170"  # 경북 안동시 (예시)
SGG = "47170"  # 시군구코드도 5자리라 데모에선 emd_code와 동일하게 사용


def _seed(conn):
    conn.execute(
        "INSERT INTO ADMIN_REGION (emd_code, grid_nx, grid_ny) VALUES (?, ?, ?)",
        (EMD, 89, 91),
    )
    conn.execute(
        "INSERT INTO WEATHER_ALERT (grid_nx, grid_ny, announce_time, alert_type, temperature, feels_like, humidity) "
        "VALUES (89, 91, '2026-08-22T14:00', '폭염경보', 36.2, 39.5, 55)"
    )
    conn.execute(
        "INSERT INTO HEAT_ILLNESS (sigungu_code, occur_date, patient_count, is_death, age_group) "
        "VALUES (?, '2026-08-21', 3, 0, '70대')",
        (SGG,),
    )
    conn.execute(
        "INSERT INTO WELFARE_FACILITY (facility_id, emd_code, name, facility_type, lat, lon) "
        "VALUES ('WF001', ?, '안동노인복지관', '노인복지관', 36.5684, 128.7294)",
        (EMD,),
    )
    conn.commit()


def test_all_three_tools_return_seeded_rows():
    conn = get_conn(":memory:")
    _seed(conn)

    alerts = _get_heatwave_alert(conn, EMD)
    assert len(alerts) == 1 and alerts[0]["alert_type"] == "폭염경보", alerts

    illness = _get_heat_illness_status(conn, SGG)
    assert len(illness) == 1 and illness[0]["patient_count"] == 3, illness

    facilities = _get_welfare_facilities(conn, EMD)
    assert len(facilities) == 1 and facilities[0]["name"] == "안동노인복지관", facilities


def test_unknown_gyeongbuk_region_returns_empty():
    """경북이지만 데이터가 없는 경우 — 빈 결과가 맞다."""
    conn = get_conn(":memory:")
    assert _get_heatwave_alert(conn, "47999") == []


def test_non_gyeongbuk_region_raises_not_empty():
    """범위 밖은 빈 결과가 아니라 에러여야 한다 — 안 그러면 에이전트가 '데이터 없음'으로 오독한다."""
    for tool, code in [
        (get_heatwave_alert, "11110"),  # 서울
        (get_heat_illness_status, "27110"),  # 대구
        (get_welfare_facilities, "48170"),  # 경남
    ]:
        try:
            tool(code)
        except ValueError as e:
            assert "대상 범위 밖" in str(e), e
        else:
            raise AssertionError(f"{tool.__name__}({code}) should have rejected out-of-scope code")


if __name__ == "__main__":
    test_all_three_tools_return_seeded_rows()
    test_unknown_gyeongbuk_region_returns_empty()
    test_non_gyeongbuk_region_raises_not_empty()
    print("OK: mcp_server.py self-check passed")
