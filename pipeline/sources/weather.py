"""기상청 초단기실황(getUltraSrtNcst) — 기온·습도만. 특보/체감온도는 별도 API 미연결."""

import os
import sqlite3
from datetime import datetime, timedelta
from urllib.parse import unquote

import requests

from pipeline.geo import latlon_to_kma_grid, upsert_admin_region

BASE_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"


def _service_key() -> str:
    # data.go.kr은 "인증키(Encoding)"/"(Decoding)" 두 버전을 준다. Encoding 버전을 그대로
    # requests params로 넘기면 %가 다시 인코딩돼 SERVICE_KEY_IS_NOT_REGISTERED_ERROR가 난다.
    # unquote로 되돌려 requests가 정확히 한 번만 인코딩하게 만든다(어느 버전을 넣어도 안전).
    return unquote(os.environ["DATA_GO_KR_SERVICE_KEY"])


def _latest_base_datetime(now: datetime | None = None) -> tuple[str, str]:
    """초단기실황은 매시 40분에 그 시각 값이 생성된다. 40분 전이면 직전 시각을 쓴다."""
    now = now or datetime.now()
    base = now if now.minute >= 40 else now - timedelta(hours=1)
    return base.strftime("%Y%m%d"), base.strftime("%H00")


def fetch_current_conditions(nx: int, ny: int) -> list[dict]:
    base_date, base_time = _latest_base_datetime()
    resp = requests.get(
        BASE_URL,
        params={
            "serviceKey": _service_key(),
            "pageNo": 1,
            "numOfRows": 20,
            "dataType": "JSON",
            "base_date": base_date,
            "base_time": base_time,
            "nx": nx,
            "ny": ny,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["response"]["body"]["items"]["item"]


def normalize(items: list[dict]) -> dict:
    """카테고리별 관측값 목록(T1H/REH/...)을 WEATHER_ALERT 한 행으로 합친다."""
    by_category = {item["category"]: item["obsrValue"] for item in items}
    first = items[0]
    return {
        "grid_nx": first["nx"],
        "grid_ny": first["ny"],
        "announce_time": f"{first['baseDate']}T{first['baseTime'][:2]}:{first['baseTime'][2:]}",
        "alert_type": None,  # 특보(경보/주의보) API 미연결 — 이 소스는 실황 관측치만 제공
        "temperature": float(by_category["T1H"]) if "T1H" in by_category else None,
        "feels_like": None,  # 생활기상지수 API 미신청
        "humidity": float(by_category["REH"]) if "REH" in by_category else None,
    }


def load(conn: sqlite3.Connection, emd_code: str, lat: float, lon: float) -> bool:
    """emd_code 지역의 현재 기온·습도를 받아 WEATHER_ALERT에 적재. 경북 밖이면 False."""
    nx, ny = latlon_to_kma_grid(lat, lon)
    if not upsert_admin_region(conn, emd_code, grid_nx=nx, grid_ny=ny, center_lat=lat, center_lon=lon):
        return False  # 경북 밖 — upsert_admin_region이 이미 안 만들었으니 API 호출도 생략

    row = normalize(fetch_current_conditions(nx, ny))
    conn.execute(
        "INSERT OR REPLACE INTO WEATHER_ALERT "
        "(grid_nx, grid_ny, announce_time, alert_type, temperature, feels_like, humidity) "
        "VALUES (:grid_nx, :grid_ny, :announce_time, :alert_type, :temperature, :feels_like, :humidity)",
        row,
    )
    conn.commit()
    return True
