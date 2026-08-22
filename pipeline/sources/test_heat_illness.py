"""Self-check for heat_illness.py. Run: python -m pipeline.sources.test_heat_illness"""

from pipeline.db import get_conn
from pipeline.sources.heat_illness import _age_group, aggregate, load, read_gyeongbuk_rows

FIXTURE_ROWS = [
    {"발생일자": "2025-08-01", "성별": "남자", "나이": "72", "발생시도": "경상북도", "발생시군구": "의성군", "실내외구분": "실외", "발생장소": "논밭"},
    {"발생일자": "2025-08-01", "성별": "여자", "나이": "74", "발생시도": "경상북도", "발생시군구": "의성군", "실내외구분": "실외", "발생장소": "논밭"},
    {"발생일자": "2025-08-01", "성별": "남자", "나이": "35", "발생시도": "경상북도", "발생시군구": "안동시", "실내외구분": "실내", "발생장소": "작업장"},
]


def test_age_group_buckets():
    assert _age_group(5) == "10대 미만"
    assert _age_group(72) == "70대"
    assert _age_group(80) == "80대 이상"
    assert _age_group(99) == "80대 이상"


def test_aggregate_counts_same_bucket_together():
    rows = aggregate(FIXTURE_ROWS)
    by_key = {(r["sigungu_name"], r["age_group"]): r["patient_count"] for r in rows}
    assert by_key[("의성군", "70대")] == 2  # 72세와 68세가 같은 버킷으로 묶임
    assert by_key[("안동시", "30대")] == 1


def test_read_gyeongbuk_rows_matches_known_screenshot_total():
    """의성군 누적 43건 — 대시보드 시안에 그대로 찍혔던 숫자와 대조(스코프 검증용)."""
    rows, skipped = read_gyeongbuk_rows()
    assert skipped > 0, "시군구 미기재 행이 실제로 있어야 스킵 로직이 검증됨"
    uiseong_total = sum(1 for r in rows if r["발생시군구"] == "의성군")
    assert uiseong_total == 43, uiseong_total


def test_load_populates_heat_illness_with_valid_sigungu_codes():
    conn = get_conn(":memory:")
    result = load(conn)

    assert result["unmapped_sigungu_names"] == [], result["unmapped_sigungu_names"]
    assert result["loaded"] > 0
    assert result["skipped_no_sigungu"] > 0

    row = conn.execute(
        "SELECT SUM(patient_count) FROM HEAT_ILLNESS WHERE sigungu_code = '4773000000'"
    ).fetchone()
    assert row[0] == 43, row  # 의성군


if __name__ == "__main__":
    test_age_group_buckets()
    test_aggregate_counts_same_bucket_together()
    test_read_gyeongbuk_rows_matches_known_screenshot_total()
    test_load_populates_heat_illness_with_valid_sigungu_codes()
    print("OK: heat_illness.py self-check passed")
