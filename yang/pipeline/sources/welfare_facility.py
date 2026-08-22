"""한국사회보장정보원_사회복지시설정보서비스 현황 — getFcltByBassInfoInqire.

jrsdSggCd(시군구코드) 필터 하나로 목록+주소가 함께 나온다(getFcltListInfoInqire를 따로
부를 필요 없음 — 원래 2단계로 계획했다가 실호출로 확인 후 1단계로 줄임).

emd_code/lat/lon은 지오코딩(JUSO_API_KEY 대기중) 전까지 비워두고 address만 저장한다.
facility_type은 코드(fcltKindCd)만 나오고 이름은 별도 "시설종류코드 조회" 오퍼레이션이
필요해서 아직 코드 그대로 저장 — 이름 매핑은 후속 작업.
"""

import os
import sqlite3
from urllib.parse import unquote

import defusedxml.ElementTree as ET

import requests

from pipeline.db import is_target_region

BASE_URL = "https://apis.data.go.kr/B554287/sclWlfrFcltInfoInqirService1/getFcltByBassInfoInqire"


def _service_key() -> str:
    return unquote(os.environ["DATA_GO_KR_SERVICE_KEY"])


def _parse_items(xml_text: str) -> tuple[list[dict], int]:
    root = ET.fromstring(xml_text)
    items = [{child.tag: child.text for child in item} for item in root.iter("item")]
    total = int(root.findtext(".//totalCount") or 0)
    return items, total


def fetch_page(jrsd_sgg_cd: str, page_no: int = 1, num_of_rows: int = 100) -> tuple[list[dict], int]:
    resp = requests.get(
        BASE_URL,
        params={
            "serviceKey": _service_key(),
            "jrsdSggCd": jrsd_sgg_cd,
            "pageNo": page_no,
            "numOfRows": num_of_rows,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return _parse_items(resp.text)


def normalize(item: dict) -> dict:
    address = " ".join(filter(None, [item.get("fcltAddr", "").strip() or None, item.get("fcltDtl_1Addr")]))
    return {
        "facility_id": item["fcltCd"],
        "name": item.get("fcltNm"),
        "facility_type": item.get("fcltKindCd"),  # 코드만 있음 — 이름 매핑은 후속 작업
        "address": address or None,
        "emd_code": None,  # 지오코딩 전까지 비움
        "lat": None,
        "lon": None,
    }


def load(conn: sqlite3.Connection, jrsd_sgg_cd: str) -> int:
    """jrsd_sgg_cd(경북 시군구코드) 관내 시설을 전부 적재하고 적재 건수를 반환. 경북 밖이면 0."""
    if not is_target_region(jrsd_sgg_cd):
        return 0

    loaded = 0
    page_no = 1
    while True:
        items, total = fetch_page(jrsd_sgg_cd, page_no=page_no, num_of_rows=100)
        if not items:
            break
        for item in items:
            if "fcltCd" not in item:
                continue  # 응답에 시설코드가 빠진 불량 레코드 — PK 없이는 못 넣음
            # jrsdSggCd 필터를 서버가 실제로 지키는지는 확인했지만(fcltCd 필터는 무시됐던 전례가
            # 있음), 이 API가 나중에 조용히 필터를 깨도 다른 지역 데이터가 안 섞이게 행 단위로도
            # 한 번 더 검사한다.
            if not is_target_region(item.get("jrsdSggCd", "")):
                continue
            row = normalize(item)
            conn.execute(
                "INSERT OR REPLACE INTO WELFARE_FACILITY "
                "(facility_id, emd_code, name, facility_type, address, lat, lon) "
                "VALUES (:facility_id, :emd_code, :name, :facility_type, :address, :lat, :lon)",
                row,
            )
            loaded += 1
        conn.commit()
        if page_no * 100 >= total:
            break
        page_no += 1
    return loaded
