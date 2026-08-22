"""경북 읍면동 중심좌표 — API 아님, 정적 파일. 승인 대기 없음(§F에서 반복된 문제 회피).

출처: 통계청 MDIS 인구용 행정경계중심점, vuski/admdongkor 저장소(CC BY 4.0)에서
경북(코드 47 접두어)만 추려 `pipeline/data/gyeongbuk_emd_centroid.tsv`로 보관.
https://github.com/vuski/admdongkor

좌표계는 EPSG:5179(UTM-K) — pipeline/geo.py의 to_wgs84로 변환. 안동시(4717000000) 대표좌표를
변환한 결과가 이전 세션에서 초단기실황 실호출로 검증된 격자(91,106)와 정확히 일치함을 확인함
(추측 아니라 기존 검증값과 대조).

코드 체계는 통계청 행정동코드지만, 경북 대부분(읍/면 지역)은 행정동=법정동이라 emd_code와
호환된다 — 시(市) 지역 동(洞) 단위 세분화가 있는 곳(포항시 남구 등)만 실제로는 행정동 기준일
수 있음. 지금 스코프(현장인력이 확인할 마을 = 읍/면 위주)에서는 문제되지 않는다.
"""

import csv
import sqlite3
from pathlib import Path

from pipeline.db import is_target_region
from pipeline.geo import latlon_to_kma_grid, to_wgs84, upsert_admin_region

_TSV_PATH = Path(__file__).parent.parent / "data" / "gyeongbuk_emd_centroid.tsv"
_UTMK_EPSG = 5179


def read_rows() -> list[dict]:
    with open(_TSV_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    out = []
    for r in rows:
        parts = r["ADMNM"].split()
        # 이름 단어 수로 시군구/읍면동 경계를 나누면 "포항시 남구"처럼 시군구명 자체가
        # 두 단어인 경우 대표행("경상북도 포항시 남구")의 마지막 단어("남구")를 읍면동으로
        # 잘못 읽는다. 코드 구조로 판별하면 이름 단어 수와 무관하게 항상 맞는다 — 법정동코드는
        # 마지막 5자리가 읍면동+리 자리라, 시군구 대표행은 그 자리가 전부 0이다.
        is_sigungu_level = r["ADMCD"].endswith("00000")
        sido = parts[0] if parts else None
        if is_sigungu_level:
            sigungu = " ".join(parts[1:]) if len(parts) > 1 else None
            emd = None
        else:
            sigungu = " ".join(parts[1:-1])
            emd = parts[-1]
        lat, lon = to_wgs84(float(r["X"]), float(r["Y"]), epsg_from=_UTMK_EPSG)
        nx, ny = latlon_to_kma_grid(lat, lon)
        out.append(
            {
                "emd_code": r["ADMCD"],
                "sido_name": sido,
                "sigungu_name": sigungu,
                "emd_name": emd,
                "center_lat": lat,
                "center_lon": lon,
                "grid_nx": nx,
                "grid_ny": ny,
            }
        )
    return out


def sigungu_code_by_name() -> dict[str, str]:
    """"의성군" 같은 이름 -> 시군구 대표코드("4773000000") 매핑.

    emd_code 앞 5자리가 시군구를 가리키고 나머지 5자리가 읍면동+리다(SSGGGDDDDD).
    포항시 남구/북구처럼 시군구 자체가 구로 갈리는 경우도 앞 5자리가 이미 그 구
    단위까지 포함돼 있어서, 별도 예외 처리 없이 아무 행에서나 뽑아도 된다.
    """
    return {r["sigungu_name"]: r["emd_code"][:5] + "00000" for r in read_rows() if r["sigungu_name"]}


def load_all(conn: sqlite3.Connection) -> int:
    """ADMIN_REGION을 경북 읍면동 중심좌표로 채운다. 경북 밖 행은 방어적으로 건너뜀."""
    count = 0
    for row in read_rows():
        if not is_target_region(row["emd_code"]):
            continue
        upsert_admin_region(conn, **row)
        count += 1
    return count
