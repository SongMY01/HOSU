import math
import os
import sqlite3

import requests
from pyproj import Transformer

from pipeline.db import is_target_region

_transformers: dict[int, Transformer] = {}

# 기상청 단기예보 격자(LCC) 변환 상수. 기상청이 공개한 공식 값 그대로이고, 하드코딩 대신
# pyproj CRS로 재현하려면 격자 원점의 false-easting/northing(XO/YO, 5km 셀 인덱스 오프셋)을
# 추측해야 해서 오히려 틀리기 쉽다 — 공식 예제 코드를 그대로 옮기는 쪽이 더 안전하다.
# 참고: https://gist.github.com/fronteer-kr/14d7f779d52a21ac2f16 (검증용 테스트케이스 포함)
_KMA_RE = 6371.00877
_KMA_GRID = 5.0
_KMA_SLAT1 = 30.0
_KMA_SLAT2 = 60.0
_KMA_OLON = 126.0
_KMA_OLAT = 38.0
_KMA_XO = 43
_KMA_YO = 136


def latlon_to_kma_grid(lat: float, lon: float) -> tuple[int, int]:
    """WGS84 (lat, lon)을 기상청 단기예보 격자좌표 (nx, ny)로 변환."""
    deg2rad = math.pi / 180.0
    re = _KMA_RE / _KMA_GRID
    slat1, slat2 = _KMA_SLAT1 * deg2rad, _KMA_SLAT2 * deg2rad
    olon, olat = _KMA_OLON * deg2rad, _KMA_OLAT * deg2rad

    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = math.pow(sf, sn) * math.cos(slat1) / sn
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re * sf / math.pow(ro, sn)

    ra = math.tan(math.pi * 0.25 + lat * deg2rad * 0.5)
    ra = re * sf / math.pow(ra, sn)
    theta = lon * deg2rad - olon
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn

    nx = math.floor(ra * math.sin(theta) + _KMA_XO + 0.5)
    ny = math.floor(ro - ra * math.cos(theta) + _KMA_YO + 0.5)
    return int(nx), int(ny)


def to_wgs84(x: float, y: float, epsg_from: int) -> tuple[float, float]:
    """Project (x, y) in the given EPSG CRS to (lat, lon) in WGS84."""
    transformer = _transformers.get(epsg_from)
    if transformer is None:
        transformer = Transformer.from_crs(f"EPSG:{epsg_from}", "EPSG:4326", always_xy=True)
        _transformers[epsg_from] = transformer
    lon, lat = transformer.transform(x, y)
    return lat, lon


def search_address(address: str) -> dict | None:
    """행안부 주소검색 API(addrLinkApi.do) — 확인된 사실만 구현. 좌표는 안 준다.

    이 응답에서 확실히 쓰는 필드(admCd)만 여기서 꺼낸다. 나머지는 raw dict로 그대로 반환.
    """
    api_key = os.environ.get("JUSO_API_KEY")
    if not api_key:
        raise RuntimeError(
            "JUSO_API_KEY not set — run `cp .env.example .env`, then fill in the key "
            "issued at business.juso.go.kr"
        )

    resp = requests.get(
        "https://www.juso.go.kr/addrlink/addrLinkApi.do",
        params={
            "confmKey": api_key,
            "currentPage": 1,
            "countPerPage": 1,
            "keyword": address,
            "resultType": "json",
        },
        timeout=10,
    )
    resp.raise_for_status()
    juso_list = resp.json()["results"]["juso"]
    return juso_list[0] if juso_list else None


def geocode_address(address: str) -> tuple[float, float, str] | None:
    """주소 → (lat, lon, bdong_code).

    확인된 사실: addrLinkApi.do(주소검색)는 좌표를 안 준다 — entX/entY는 별도
    addrCoordApi.do(좌표제공) 호출로 받아야 한다. 그 두 번째 호출의 정확한 요청
    파라미터명(admCd 다음에 rnMgtSn/udrtYn/buldMnnm/buldSlno 등이 필요할 것으로
    보이나 공식 문서를 못 읽어서 미확정)은 실제 JUSO_API_KEY로 응답을 봐야 확정할 수
    있다. 여기서 추측한 필드명으로 구현하면 이전에 entX/entY 위치를 잘못 짚었던
    실수를 그대로 반복하는 셈이라, 검증 전에는 명확히 미구현으로 남긴다.
    """
    juso = search_address(address)
    if juso is None:
        return None
    raise NotImplementedError(
        f"주소검색까지는 됨(admCd={juso['admCd']}) — 좌표제공 API(addrCoordApi.do) 연동은 "
        "실제 JUSO_API_KEY로 응답 확인 후 구현 예정. WELFARE_FACILITY 소스가 정해지고 "
        "키가 발급되면 이어서 작업."
    )


def upsert_admin_region(conn: sqlite3.Connection, emd_code: str, **fields) -> bool:
    """Lazily create/fill an ADMIN_REGION row. Only writes columns that are currently NULL.

    Rows outside the target province are skipped and return False, so a loader walking a
    nationwide API response can do `if not upsert_admin_region(...): continue` and drop the
    dependent row too. This is the single gate that keeps the store Gyeongbuk-only.
    """
    if not is_target_region(emd_code):
        return False

    conn.execute("INSERT OR IGNORE INTO ADMIN_REGION (emd_code) VALUES (?)", (emd_code,))

    if not fields:
        conn.commit()
        return True

    row = conn.execute(
        "SELECT * FROM ADMIN_REGION WHERE emd_code = ?", (emd_code,)
    ).fetchone()
    columns = [d[0] for d in conn.execute("SELECT * FROM ADMIN_REGION LIMIT 0").description]
    current = dict(zip(columns, row))

    to_fill = {k: v for k, v in fields.items() if current.get(k) is None and v is not None}
    if to_fill:
        set_clause = ", ".join(f"{k} = ?" for k in to_fill)
        conn.execute(
            f"UPDATE ADMIN_REGION SET {set_clause} WHERE emd_code = ?",
            (*to_fill.values(), emd_code),
        )
    conn.commit()
    return True
