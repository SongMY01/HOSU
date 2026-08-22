"""Self-check for pipeline/geo.py. Run: python -m pipeline.test_geo"""

from pyproj import Transformer

from pipeline.db import get_conn
from pipeline.geo import latlon_to_kma_grid, to_wgs84, upsert_admin_region

# Andong city hall, approx WGS84 (경북 안동시청)
ANDONG_LAT, ANDONG_LON = 36.5684, 128.7294


def test_to_wgs84_roundtrip():
    """Project a known WGS84 point into EPSG:5179 and back; to_wgs84 must recover it."""
    forward = Transformer.from_crs("EPSG:4326", "EPSG:5179", always_xy=True)
    x, y = forward.transform(ANDONG_LON, ANDONG_LAT)

    lat, lon = to_wgs84(x, y, epsg_from=5179)

    assert abs(lat - ANDONG_LAT) < 1e-6, f"lat drift: {lat} vs {ANDONG_LAT}"
    assert abs(lon - ANDONG_LON) < 1e-6, f"lon drift: {lon} vs {ANDONG_LON}"
    # sanity: still inside Korea's bounding box
    assert 33 < lat < 39 and 124 < lon < 132


def test_upsert_admin_region_idempotent_and_fills_only_nulls():
    conn = get_conn(":memory:")

    upsert_admin_region(conn, "47170", sido_name="경상북도", sigungu_name="안동시")
    upsert_admin_region(conn, "47170", sido_name="경상북도(중복입력)", emd_name="풍산읍")

    row = conn.execute(
        "SELECT sido_name, sigungu_name, emd_name FROM ADMIN_REGION WHERE emd_code = ?",
        ("47170",),
    ).fetchone()

    assert row == ("경상북도", "안동시", "풍산읍"), row  # first write wins, second only fills the gap

    count = conn.execute("SELECT COUNT(*) FROM ADMIN_REGION").fetchone()[0]
    assert count == 1, "upsert must not create duplicate rows"


def test_latlon_to_kma_grid_matches_known_reference():
    """왕복이 아니라 기상청 공식 예제의 실제 기준값과 대조 — 서울시청 인근 (60, 127)."""
    nx, ny = latlon_to_kma_grid(37.579871128849334, 126.98935225645432)
    assert (nx, ny) == (60, 127), (nx, ny)


def test_upsert_admin_region_drops_non_gyeongbuk():
    """The ingest gate is what keeps the store Gyeongbuk-only."""
    conn = get_conn(":memory:")

    assert upsert_admin_region(conn, "47170", emd_name="안동시") is True
    assert upsert_admin_region(conn, "11110", emd_name="서울 종로구") is False  # 서울
    assert upsert_admin_region(conn, "27110", emd_name="대구 중구") is False  # 대구는 경북 아님

    codes = [r[0] for r in conn.execute("SELECT emd_code FROM ADMIN_REGION").fetchall()]
    assert codes == ["47170"], codes


if __name__ == "__main__":
    test_to_wgs84_roundtrip()
    test_latlon_to_kma_grid_matches_known_reference()
    test_upsert_admin_region_idempotent_and_fills_only_nulls()
    test_upsert_admin_region_drops_non_gyeongbuk()
    print("OK: geo.py self-check passed")
