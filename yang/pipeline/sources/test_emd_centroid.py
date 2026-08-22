"""Self-check for emd_centroid.py. Run: python -m pipeline.sources.test_emd_centroid"""

from pipeline.db import get_conn
from pipeline.sources.emd_centroid import load_all, read_rows


def test_read_rows_parses_known_region():
    rows = {r["emd_code"]: r for r in read_rows()}

    dain = rows["4773044000"]  # 의성군 다인면
    assert dain["sido_name"] == "경상북도"
    assert dain["sigungu_name"] == "의성군"
    assert dain["emd_name"] == "다인면"
    assert 36.0 < dain["center_lat"] < 37.0
    assert 128.0 < dain["center_lon"] < 129.0

    andong = rows["4717000000"]  # 안동시 (시군구 대표 좌표)
    # 이전 세션에서 초단기실황 실호출로 검증된 격자값과 정확히 일치해야 한다.
    assert (andong["grid_nx"], andong["grid_ny"]) == (91, 106), andong


def test_two_word_sigungu_representative_row_parses_correctly():
    """'포항시 남구' 대표행 자체는 '경상북도 포항시 남구'(3단어)라, 이름 토큰 수로만 자르면
    마지막 단어 '남구'를 읍면동으로 잘못 읽는다 — 코드가 00000으로 끝나는지로 판별해야 한다."""
    rows = {r["emd_code"]: r for r in read_rows()}
    namgu = rows["4711100000"]
    assert namgu["sigungu_name"] == "포항시 남구", namgu
    assert namgu["emd_name"] is None, namgu

    # 진짜 하위 읍면동(4단어: "경상북도 포항시 남구 구룡포읍")은 그대로 잘 갈라져야 한다.
    guryongpo = rows["4711125000"]
    assert guryongpo["sigungu_name"] == "포항시 남구", guryongpo
    assert guryongpo["emd_name"] == "구룡포읍", guryongpo


def test_all_rows_are_gyeongbuk():
    for r in read_rows():
        assert r["emd_code"].startswith("47"), r


def test_load_all_populates_admin_region():
    conn = get_conn(":memory:")
    count = load_all(conn)

    assert count > 200, count  # 경북 읍면동+시군구 대표 행 전체
    total = conn.execute("SELECT COUNT(*) FROM ADMIN_REGION").fetchone()[0]
    assert total == count

    row = conn.execute(
        "SELECT emd_name, grid_nx, grid_ny FROM ADMIN_REGION WHERE emd_code = '4773044000'"
    ).fetchone()
    assert row[0] == "다인면", row


if __name__ == "__main__":
    test_read_rows_parses_known_region()
    test_two_word_sigungu_representative_row_parses_correctly()
    test_all_rows_are_gyeongbuk()
    test_load_all_populates_admin_region()
    print("OK: emd_centroid.py self-check passed")
