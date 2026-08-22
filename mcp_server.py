import sqlite3

from mcp.server.mcpserver import MCPServer

from pipeline.db import TARGET_SIDO_NAME, get_conn, require_target_region

mcp = MCPServer(
    "hosu-heat-copilot",
    instructions=f"{TARGET_SIDO_NAME} 폭염 대응 데이터 조회. 이 서버는 {TARGET_SIDO_NAME} 지역만 다룬다.",
)


def _get_heatwave_alert(conn: sqlite3.Connection, emd_code: str) -> list[dict]:
    row = conn.execute(
        "SELECT grid_nx, grid_ny FROM ADMIN_REGION WHERE emd_code = ?", (emd_code,)
    ).fetchone()
    if row is None:
        return []
    nx, ny = row
    cols = ["announce_time", "alert_type", "temperature", "feels_like", "humidity"]
    rows = conn.execute(
        f"SELECT {', '.join(cols)} FROM WEATHER_ALERT "
        "WHERE grid_nx = ? AND grid_ny = ? ORDER BY announce_time DESC LIMIT 5",
        (nx, ny),
    ).fetchall()
    return [dict(zip(cols, r)) for r in rows]


@mcp.tool()
def get_heatwave_alert(emd_code: str) -> list[dict]:
    """emd_code(경북 행정동코드) 지역의 최신 폭염특보·기온 정보를 조회한다."""
    require_target_region(emd_code)
    return _get_heatwave_alert(get_conn(), emd_code)


def _get_heat_illness_status(conn: sqlite3.Connection, sigungu_code: str) -> list[dict]:
    cols = ["occur_date", "patient_count", "is_death", "age_group"]
    rows = conn.execute(
        f"SELECT {', '.join(cols)} FROM HEAT_ILLNESS "
        "WHERE sigungu_code = ? ORDER BY occur_date DESC LIMIT 30",
        (sigungu_code,),
    ).fetchall()
    return [dict(zip(cols, r)) for r in rows]


@mcp.tool()
def get_heat_illness_status(sigungu_code: str) -> list[dict]:
    """sigungu_code(경북 시군구코드) 지역의 최근 온열질환 발생 현황을 조회한다."""
    require_target_region(sigungu_code)
    return _get_heat_illness_status(get_conn(), sigungu_code)


def _get_elderly_living_alone_density(conn: sqlite3.Connection, sigungu_code: str) -> dict | None:
    cols = ["year", "age_65_69", "age_70_74", "age_75_79", "age_80_84", "age_85_over"]
    row = conn.execute(
        f"SELECT {', '.join(cols)} FROM ELDERLY_ALONE "
        "WHERE sigungu_code = ? ORDER BY year DESC LIMIT 1",
        (sigungu_code,),
    ).fetchone()
    return dict(zip(cols, row)) if row else None


@mcp.tool()
def get_elderly_living_alone_density(sigungu_code: str) -> dict | None:
    """sigungu_code(경북 시군구코드) 지역의 최신 연도 독거노인 연령대별 인원을 조회한다."""
    require_target_region(sigungu_code)
    return _get_elderly_living_alone_density(get_conn(), sigungu_code)


def _get_welfare_facilities(conn: sqlite3.Connection, emd_code: str) -> list[dict]:
    cols = ["facility_id", "name", "facility_type", "lat", "lon"]
    rows = conn.execute(
        f"SELECT {', '.join(cols)} FROM WELFARE_FACILITY WHERE emd_code = ?", (emd_code,)
    ).fetchall()
    return [dict(zip(cols, r)) for r in rows]


@mcp.tool()
def get_welfare_facilities(emd_code: str) -> list[dict]:
    """emd_code(경북 행정동코드) 지역 내 복지시설 목록을 조회한다."""
    require_target_region(emd_code)
    return _get_welfare_facilities(get_conn(), emd_code)


if __name__ == "__main__":
    mcp.run()
