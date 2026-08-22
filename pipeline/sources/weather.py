"""기상청 초단기실황(getUltraSrtNcst) — 기온·습도만. 특보/체감온도는 별도 API 미연결."""

import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
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


# 기상청 결측 센티널. -999(결측)/-998(관측불가)를 HTTP 200에 정상 응답 형태로 준다 —
# 격자 범위 밖 nx/ny를 넣으면 에러가 아니라 이 값이 돌아온다(실호출로 확인).
# 그대로 float으로 넘기면 기온 -999도가 저장돼 위험도 계산이 조용히 망가진다.
_MISSING_THRESHOLD = -900.0


def _obs_value(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return None if value <= _MISSING_THRESHOLD else value


def normalize(items: list[dict]) -> dict:
    """카테고리별 관측값 목록(T1H/REH/...)을 WEATHER_ALERT 한 행으로 합친다."""
    by_category = {item["category"]: item["obsrValue"] for item in items}
    first = items[0]
    return {
        "grid_nx": first["nx"],
        "grid_ny": first["ny"],
        "announce_time": f"{first['baseDate']}T{first['baseTime'][:2]}:{first['baseTime'][2:]}",
        "alert_type": None,  # 특보(경보/주의보) API 미연결 — 이 소스는 실황 관측치만 제공
        "temperature": _obs_value(by_category.get("T1H")),
        "feels_like": None,  # 생활기상지수 API 미신청
        "humidity": _obs_value(by_category.get("REH")),
    }


def load(conn: sqlite3.Connection, emd_code: str, lat: float, lon: float) -> bool:
    """emd_code 지역의 현재 기온·습도를 받아 WEATHER_ALERT에 적재. 경북 밖이면 False."""
    nx, ny = latlon_to_kma_grid(lat, lon)
    if not upsert_admin_region(conn, emd_code, grid_nx=nx, grid_ny=ny, center_lat=lat, center_lon=lon):
        return False  # 경북 밖 — upsert_admin_region이 이미 안 만들었으니 API 호출도 생략

    row = normalize(fetch_current_conditions(nx, ny))
    conn.execute(_INSERT_SQL, row)
    conn.commit()
    return True


_INSERT_SQL = (
    "INSERT OR REPLACE INTO WEATHER_ALERT "
    "(grid_nx, grid_ny, announce_time, alert_type, temperature, feels_like, humidity) "
    "VALUES (:grid_nx, :grid_ny, :announce_time, :alert_type, :temperature, :feels_like, :humidity)"
)

# 동시 호출 수. 경북 읍면동 417개가 5km 격자로는 302개라 그만큼 호출이 나가는데, 순차로는
# 1분 반 정도 걸린다. 8이면 십수 초로 줄면서 data.go.kr에 무리도 안 준다.
# ponytail: 고정값. data.go.kr이 429를 주기 시작하면 그때 낮춘다.
_MAX_WORKERS = 8


def _freshness_cutoff(now: datetime | None = None) -> str:
    """이 시각 이후 announce_time을 가진 행은 최신으로 간주한다(= 재호출 생략).

    기준시각과 정확히 일치하는지로 판정하면 안 된다. 기상청 발표가 늦어져 직전 시각 값이
    내려오면, 그걸 저장해도 다음 실행에서 또 기준시각과 안 맞아 미스가 나고, 결국 매번
    전량 재호출하는 캐시가 된다. 한 시간 여유를 둬서 그 무한 재호출을 끊는다.
    """
    base_date, base_time = _latest_base_datetime(now)
    base = datetime.strptime(base_date + base_time, "%Y%m%d%H%M") - timedelta(hours=1)
    return base.strftime("%Y%m%dT%H:%M")


def _fetch_one(grid: tuple[int, int]) -> tuple[dict | None, str | None]:
    """격자 하나를 받아온다. 실패를 예외로 던지지 않는다 — 격자 하나 때문에 배치 전체가
    죽으면 302개 중 301개 성공분까지 같이 날아간다."""
    nx, ny = grid
    try:
        return normalize(fetch_current_conditions(nx, ny)), None
    except Exception as e:
        return None, f"({nx},{ny}) {type(e).__name__}: {e}"


def refresh_all(conn: sqlite3.Connection, force: bool = False) -> dict:
    """ADMIN_REGION에 등록된 모든 격자의 실황을 받아 WEATHER_ALERT에 적재.

    캐시는 별도 계층 없이 WEATHER_ALERT 자체다 — PK가 이미
    (grid_nx, grid_ny, announce_time)이라 "이번 시각 데이터가 이미 있나"가 곧 캐시 조회고,
    시간이 넘어가면 키가 바뀌므로 만료 처리도 공짜다.

    HTTP만 병렬로 돌리고 DB 쓰기는 전부 이 스레드에서 한다 — sqlite3 커넥션을 워커에
    넘기지 않으므로 스레드 안전성 문제가 아예 생기지 않는다.
    """
    all_grids = [
        (r[0], r[1])
        for r in conn.execute(
            "SELECT DISTINCT grid_nx, grid_ny FROM ADMIN_REGION "
            "WHERE grid_nx IS NOT NULL AND grid_ny IS NOT NULL"
        )
    ]

    targets = all_grids
    if not force:
        fresh = {
            (r[0], r[1])
            for r in conn.execute(
                "SELECT grid_nx, grid_ny FROM WEATHER_ALERT WHERE announce_time >= ? "
                "GROUP BY grid_nx, grid_ny",
                (_freshness_cutoff(),),
            )
        }
        targets = [g for g in all_grids if g not in fresh]

    results = []
    if targets:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
            results = list(ex.map(_fetch_one, targets))

    rows = [row for row, _ in results if row is not None]
    errors = [err for _, err in results if err is not None]

    if rows:
        conn.executemany(_INSERT_SQL, rows)
        conn.commit()

    return {
        "grids": len(all_grids),
        "cached": len(all_grids) - len(targets),
        "loaded": len(rows),
        "failed": len(errors),
        "errors": errors,
    }


if __name__ == "__main__":
    # 데모 준비용 프리페치. ADMIN_REGION(경북 읍면동 좌표)을 먼저 채운 뒤 실황을 받아온다.
    from dotenv import load_dotenv

    from pipeline.db import get_conn
    from pipeline.sources.emd_centroid import load_all

    load_dotenv()
    conn = get_conn()
    print(f"ADMIN_REGION: {load_all(conn)}개 읍면동 적재")
    result = refresh_all(conn)
    print(
        f"격자 {result['grids']}개 중 캐시 적중 {result['cached']}, "
        f"신규 적재 {result['loaded']}, 실패 {result['failed']}"
    )
    for err in result["errors"][:10]:
        print("  실패:", err)
