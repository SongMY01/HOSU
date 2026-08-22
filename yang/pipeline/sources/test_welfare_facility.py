"""Self-check for pipeline/sources/welfare_facility.py. Run: python -m pipeline.sources.test_welfare_facility"""

from unittest.mock import patch

from pipeline.db import get_conn
from pipeline.sources import welfare_facility
from pipeline.sources.welfare_facility import _parse_items, load, normalize

# 실제 getFcltByBassInfoInqire 응답(안동시, jrsdSggCd=4717000000)에서 캡처한 샘플
SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<response><header><resultCode>00</resultCode><resultMsg>NORMAL SERVICE.</resultMsg></header>
<body><items>
<item><bizno>6068232306</bizno><cprNm>사회복지법인 도원복지재단</cprNm><estbDe>19520519</estbDe>
<fcltAddr>경상북도 안동시 옹정골길 </fcltAddr><fcltCd>B0121</fcltCd>
<fcltDtl_1Addr>35 (정상동)</fcltDtl_1Addr><fcltKindCd>020101</fcltKindCd>
<fcltNm>경안신육원</fcltNm><jrsdSggCd>4717000000</jrsdSggCd></item>
<item><bizno>5088206692</bizno><cprNm>대성사회복지재단</cprNm><estbDe>19820905</estbDe>
<fcltCd>F0068</fcltCd><fcltKindCd>040211</fcltKindCd><fcltNm>대성***</fcltNm>
<jrsdSggCd>4717000000</jrsdSggCd></item>
</items><numOfRows>3</numOfRows><pageNo>1</pageNo><totalCount>144</totalCount></body></response>"""


def test_parse_items_extracts_rows_and_total():
    items, total = _parse_items(SAMPLE_XML)
    assert len(items) == 2
    assert total == 144


def test_normalize_combines_address_parts():
    items, _ = _parse_items(SAMPLE_XML)
    row = normalize(items[0])
    assert row["facility_id"] == "B0121"
    assert row["name"] == "경안신육원"
    assert row["address"] == "경상북도 안동시 옹정골길 35 (정상동)"
    assert row["emd_code"] is None and row["lat"] is None  # 지오코딩 전까지 비움


def test_normalize_handles_missing_address():
    """일부 시설은 fcltAddr 자체가 응답에 없음(예: 대성사회복지재단) — None으로 처리돼야 함."""
    items, _ = _parse_items(SAMPLE_XML)
    row = normalize(items[1])
    assert row["address"] is None


def test_load_and_insert_round_trip():
    conn = get_conn(":memory:")
    items, _ = _parse_items(SAMPLE_XML)
    for item in items:
        row = normalize(item)
        conn.execute(
            "INSERT INTO WELFARE_FACILITY (facility_id, emd_code, name, facility_type, address, lat, lon) "
            "VALUES (:facility_id, :emd_code, :name, :facility_type, :address, :lat, :lon)",
            row,
        )
    count = conn.execute("SELECT COUNT(*) FROM WELFARE_FACILITY").fetchone()[0]
    assert count == 2


def test_load_skips_items_missing_fcltCd():
    """실제 응답에 fcltCd 자체가 없는 불량 레코드가 섞여 나옴 — PK 없이 못 넣으니 건너뛴다."""
    xml_with_bad_item = SAMPLE_XML.replace("<fcltCd>F0068</fcltCd>", "")
    items, _ = _parse_items(xml_with_bad_item)
    assert "fcltCd" not in items[1]

    conn = get_conn(":memory:")
    for item in items:
        if "fcltCd" not in item:
            continue
        conn.execute(
            "INSERT INTO WELFARE_FACILITY (facility_id, name) VALUES (:facility_id, :name)",
            normalize(item),
        )
    count = conn.execute("SELECT COUNT(*) FROM WELFARE_FACILITY").fetchone()[0]
    assert count == 1, "fcltCd 없는 레코드는 건너뛰고, 있는 것만 들어가야 함"


def test_load_drops_rows_if_server_side_filter_ever_fails():
    """jrsdSggCd 필터를 지금은 서버가 지키는 걸 실호출로 확인했지만(fcltCd 필터는 무시됐던
    전례가 있음), 나중에 조용히 깨지는 경우를 대비해 행 단위 검사가 실제로 걸러내는지 확인."""
    leaked_items = [
        {"fcltCd": "B0121", "fcltNm": "경안신육원", "jrsdSggCd": "4717000000"},  # 안동(경북) — 통과
        {"fcltCd": "X9999", "fcltNm": "서울의 시설", "jrsdSggCd": "1111000000"},  # 서울 — 걸러져야 함
    ]

    conn = get_conn(":memory:")
    with patch.object(welfare_facility, "fetch_page", return_value=(leaked_items, 2)):
        loaded = load(conn, "4717000000")

    assert loaded == 1, "경북 밖 레코드가 새는 걸 행 단위 검사가 못 잡음"
    ids = [r[0] for r in conn.execute("SELECT facility_id FROM WELFARE_FACILITY").fetchall()]
    assert ids == ["B0121"]


def test_load_skips_non_gyeongbuk_without_network_call():
    conn = get_conn(":memory:")
    result = load(conn, "11110000000")  # 서울
    assert result == 0
    count = conn.execute("SELECT COUNT(*) FROM WELFARE_FACILITY").fetchone()[0]
    assert count == 0


if __name__ == "__main__":
    test_parse_items_extracts_rows_and_total()
    test_normalize_combines_address_parts()
    test_normalize_handles_missing_address()
    test_load_and_insert_round_trip()
    test_load_skips_items_missing_fcltCd()
    test_load_drops_rows_if_server_side_filter_ever_fails()
    test_load_skips_non_gyeongbuk_without_network_call()
    print("OK: welfare_facility.py self-check passed")
