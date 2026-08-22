"""Self-check for build_prototype.py's data-shaping functions.
Run: python test_build_prototype.py

두 단어짜리 시군구명("포항시 남구")이 회귀 대상 — 처음 구현에서 이 케이스 때문에
온열질환 레이어에서 24개 중 2개(포항시 남구·북구)가 조용히 빠졌었다."""

from build_prototype import build_illness_points, build_points
from pipeline.db import get_conn


def _seed(conn):
    # 남구/북구처럼 두 단어 시군구명을 포함해서 검증한다.
    regions = [
        ("4717025000", "안동시", "풍산읍", 36.6, 128.6, 91, 106),
        ("4711125000", "포항시 남구", "구룡포읍", 35.9, 129.5, 102, 94),
        ("4711100000", "포항시 남구", None, 35.98, 129.36, 102, 95),  # 시군구 대표행 자체
    ]
    for emd_code, sgg, emd, lat, lon, nx, ny in regions:
        conn.execute(
            "INSERT INTO ADMIN_REGION (emd_code, sigungu_name, emd_name, center_lat, center_lon, grid_nx, grid_ny) "
            "VALUES (?,?,?,?,?,?,?)",
            (emd_code, sgg, emd, lat, lon, nx, ny),
        )
    conn.execute(
        "INSERT INTO WEATHER_ALERT (grid_nx, grid_ny, announce_time, temperature, humidity) "
        "VALUES (91, 106, '2026-08-23T00:00', 30.0, 60), (102, 94, '2026-08-23T00:00', 33.0, 80)"
    )
    conn.execute(
        "INSERT INTO HEAT_ILLNESS (sigungu_code, occur_date, age_group, patient_count) VALUES "
        "('4717000000', '2025-08-01', '70대', 5), "
        "('4711100000', '2025-08-01', '60대', 9)"  # 포항시 남구 — 두 단어 케이스
    )
    conn.commit()


def test_build_points_skips_grid_without_weather():
    conn = get_conn(":memory:")
    _seed(conn)
    points = build_points(conn)
    # 풍산읍(91,106)·구룡포읍(102,94)엔 기상값이 있고, 남구 대표행(102,95)엔 없음(emd_name
    # 도 None이라 애초에 leaf가 아님) -> leaf 중 기상 있는 2개만 나와야 한다.
    assert len(points) == 2, points
    assert {p["emd_name"] for p in points} == {"풍산읍", "구룡포읍"}


def test_build_illness_points_includes_two_word_sigungu():
    """회귀 확인: '포항시 남구'가 온열질환 레이어에서 누락되면 안 된다."""
    conn = get_conn(":memory:")
    _seed(conn)
    illness = build_illness_points(conn)
    names = {p["sigungu_name"] for p in illness}
    assert "포항시 남구" in names, names
    assert "안동시" in names, names
    assert len(illness) == 2, illness


if __name__ == "__main__":
    test_build_points_skips_grid_without_weather()
    test_build_illness_points_includes_two_word_sigungu()
    print("OK: build_prototype.py self-check passed")
