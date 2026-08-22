"""질병관리청 온열질환 감시 데이터 — API 아님, 사용자가 받아온 개별 환자 단위 CSV(§E).

원본 컬럼: 발생일자, 성별, 나이, 발생시도, 발생시군구, 실내외구분, 발생장소. 사망 여부는
이 파일에 없어서 HEAT_ILLNESS.is_death는 항상 NULL로 남긴다(추측 대신 미확인으로 표시).

경북 행 중 37%(2500건 중 915건)는 발생시군구가 비어 있다 — 어느 시군구인지 특정할 수 없는
행이라 sigungu_code NOT NULL 제약을 못 채운다. 시도 전체로 뭉뚱그려 배정하면 실제로는 없던
지역별 차이를 만들어내므로, 추측 대신 건너뛴다(skipped 카운트로 보고).

읍면동 단위 데이터가 아니다 — 원본 자체가 시군구까지만 준다. 세분화는 불가능(SPEC §7).
"""

import csv
import sqlite3
from collections import Counter
from pathlib import Path

from pipeline.sources.emd_centroid import sigungu_code_by_name

_DEFAULT_CSV_PATH = Path(__file__).parent.parent / "data" / "질병관리청_온열질환 감시 데이터_20250925.CSV"
_TARGET_SIDO = "경상북도"


def _age_group(age: int) -> str:
    if age < 10:
        return "10대 미만"
    if age >= 80:
        return "80대 이상"
    return f"{(age // 10) * 10}대"


def read_gyeongbuk_rows(csv_path: Path = _DEFAULT_CSV_PATH) -> tuple[list[dict], int]:
    """경북 행만 골라 반환. (행 목록, 시군구 없어서 건너뛴 행 수)."""
    rows = []
    skipped = 0
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if not row["발생일자"] or row["발생시도"] != _TARGET_SIDO:
                continue
            if not row["발생시군구"].strip():
                skipped += 1
                continue
            rows.append(row)
    return rows, skipped


def aggregate(rows: list[dict]) -> list[dict]:
    """개별 환자 행 -> (sigungu_name, occur_date, age_group)별 건수."""
    counts = Counter(
        (row["발생시군구"], row["발생일자"], _age_group(int(row["나이"]))) for row in rows
    )
    return [
        {"sigungu_name": sgg, "occur_date": date, "age_group": age_group, "patient_count": n}
        for (sgg, date, age_group), n in counts.items()
    ]


def load(conn: sqlite3.Connection, csv_path: Path = _DEFAULT_CSV_PATH) -> dict:
    rows, skipped_no_sigungu = read_gyeongbuk_rows(csv_path)
    code_by_name = sigungu_code_by_name()

    to_insert = []
    unmapped_names = set()
    for agg in aggregate(rows):
        code = code_by_name.get(agg["sigungu_name"])
        if code is None:
            unmapped_names.add(agg["sigungu_name"])
            continue
        to_insert.append(
            {
                "sigungu_code": code,
                "occur_date": agg["occur_date"],
                "age_group": agg["age_group"],
                "patient_count": agg["patient_count"],
                "is_death": None,
            }
        )

    conn.executemany(
        "INSERT OR REPLACE INTO HEAT_ILLNESS "
        "(sigungu_code, occur_date, age_group, patient_count, is_death) "
        "VALUES (:sigungu_code, :occur_date, :age_group, :patient_count, :is_death)",
        to_insert,
    )
    conn.commit()

    return {
        "loaded": len(to_insert),
        "skipped_no_sigungu": skipped_no_sigungu,
        "unmapped_sigungu_names": sorted(unmapped_names),
    }


if __name__ == "__main__":
    from pipeline.db import get_conn

    conn = get_conn()
    result = load(conn)
    print(
        f"HEAT_ILLNESS: {result['loaded']}행 적재, "
        f"시군구 없어서 제외 {result['skipped_no_sigungu']}건"
    )
    if result["unmapped_sigungu_names"]:
        print("매핑 실패한 시군구명:", result["unmapped_sigungu_names"])
