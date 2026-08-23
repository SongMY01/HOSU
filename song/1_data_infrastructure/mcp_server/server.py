"""
HOSU MCP 서버
경북 폭염 위험도 데이터를 AI가 즉시 사용할 수 있는 Tool로 노출한다.

파이프라인이 미리 계산해 둔 SQLite를 read-only로 조회하고,
실시간 요소(체감온도)만 호출 시점에 기상청 API로 가져와 결합한다.

실행: python mcp_server/server.py
사전 조건: python pipeline/build.py 로 data/hosu.db 생성
"""

import math
import os
import sqlite3
from datetime import datetime
try:                                            # MCP SDK 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:                             # MCP SDK 1.x
    from mcp.server.fastmcp import FastMCP as _Server

import sys
_SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

from weather import get_feels_like, get_weather_details, temp_to_level, LEVEL_SCORE

BASE_DIR = os.path.dirname(_SERVER_DIR)
DB_PATH = os.path.join(BASE_DIR, "data", "hosu.db")

# 최종 위험도 = 정적 기저 위험도 * (1 - a) + 실시간 기온 위험도 * a
REALTIME_WEIGHT = 0.4

mcp = _Server(
    "hosu-heat-risk",
    instructions="경상북도 폭염 위험도와 대응 채널 커버리지를 조회하는 도구 모음. "
                 "모든 데이터는 행정구역 단위 집계이며 개인정보를 포함하지 않는다.",
)


def q(sql, params=()):
    if not os.path.exists(DB_PATH):
        raise RuntimeError("data/hosu.db 없음. `python pipeline/build.py` 를 먼저 실행하세요.")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def resolve_region(region: str):
    """행정코드 또는 지역명(단일/복합)으로 지역 1건을 찾는다."""
    region = region.strip()
    # 1. 행정코드 직접 매칭
    rows = q("SELECT * FROM regions WHERE region_code = ?", (region,))
    if rows:
        return rows[0]

    # 2. 단일 이름 일치
    rows = q(
        "SELECT * FROM regions WHERE sigungu = ? OR eupmyeondong = ? "
        "ORDER BY CASE level WHEN 'eupmyeondong' THEN 0 ELSE 1 END LIMIT 1",
        (region, region))
    if rows:
        return rows[0]

    # 3. 복합 이름 매칭 (예: '포항시 구룡포읍', '경북 안동시 도산면')
    tokens = region.split()
    if len(tokens) >= 2:
        sgg_cand = [t for t in tokens if t.endswith(('시', '군', '구'))]
        emd_cand = [t for t in tokens if t.endswith(('읍', '면', '동', '가'))]
        if sgg_cand and emd_cand:
            rows = q(
                "SELECT * FROM regions WHERE sigungu LIKE ? AND eupmyeondong LIKE ? LIMIT 1",
                (f"%{sgg_cand[0]}%", f"%{emd_cand[0]}%")
            )
            if rows:
                return rows[0]

    # 4. 부분 문자열 매칭
    rows = q(
        "SELECT * FROM regions WHERE (sigungu || ' ' || COALESCE(eupmyeondong, '')) LIKE ? "
        "OR eupmyeondong LIKE ? LIMIT 1",
        (f"%{region}%", f"%{region}%")
    )
    return rows[0] if rows else None


def region_label(r):
    return f"{r['sigungu']} {r['eupmyeondong']}" if r["eupmyeondong"] else r["sigungu"]


def illness_profile(region_code):
    """해당 지역이 속한 시군구의 온열질환 누적 프로파일."""
    rows = q("""
        SELECT SUM(case_count) total,
               MIN(year) from_year, MAX(year) to_year
        FROM heat_illness_history WHERE region_code = ?
    """, (region_code[:5] + "00000",))
    if not rows or not rows[0]["total"]:
        return None
    x = rows[0]
    return {
        "total_cases": x["total"],
        "from_year": x["from_year"],
        "to_year": x["to_year"],
    }


# ---------------------------------------------------------------- tools

@mcp.tool()
def get_heat_risk_score(region: str) -> dict:
    """특정 지역의 오늘자 폭염 위험도 점수와 그 근거를 반환한다.

    정적 위험 요소(고령인구·농업인·쉼터접근성·과거이력)는 파이프라인이
    사전 계산한 값을 쓰고, 실시간 체감온도만 호출 시점에 결합한다.

    Args:
        region: 행정표준코드 10자리 또는 지역명 (예: '의성군', '4772000000')
    """
    r = resolve_region(region)
    if not r:
        return {"error": f"'{region}' 지역을 찾을 수 없습니다."}

    code = r["region_code"]
    s = q("SELECT * FROM static_risk_scores WHERE region_code=?", (code,))
    if not s:
        return {"error": f"{region_label(r)}의 위험도 데이터가 없습니다."}
    s = s[0]

    w = get_weather_details(r["kma_nx"], r["kma_ny"], region_code=code, sigungu=r["sigungu"], eupmyeondong=r["eupmyeondong"])
    feels_like = w["feels_like"]
    temp = w["temperature"]
    hum = w["humidity"]
    level = temp_to_level(feels_like)
    rt_score = LEVEL_SCORE[level]

    final = s["static_total"] * (1 - REALTIME_WEIGHT) + rt_score * REALTIME_WEIGHT

    acc = q("SELECT * FROM shelter_access WHERE region_code=?", (code,))
    v = q("SELECT * FROM vulnerability WHERE region_code=?", (code,))
    acc, v = (acc[0] if acc else {}), (v[0] if v else {})

    prof = illness_profile(code)

    # 결론만이 아니라 계산에 쓴 값을 함께 반환한다 — 담당자가 검증할 수 없는 판단은
    # 현장에서 쓰이지 않으므로, 근거 문장에 산출 근거를 같이 담는다.
    reasons = []
    if rt_score >= 66:
        reasons.append(f"체감온도 {feels_like}°C — {level} 단계 기준 초과 "
                       f"(실측 기온 {temp}°C, 습도 {hum}%로 계산)")
    if s["elderly_score"] >= 60:
        basis = f" ({v['base_year']}년 기준)" if v.get("base_year") else ""
        reasons.append(f"65세 이상 인구비율 {v.get('elderly_ratio', 0) * 100:.1f}%{basis}")
    if acc.get("is_blind_spot"):
        reasons.append(f"도보 5분권(400m) 무더위쉼터 없음 — "
                       f"최근접 {acc.get('nearest_distance_m', 0):.0f}m")
    if prof and prof["total_cases"] and s["history_score"] >= 60:
        reasons.append(f"{r['sigungu']} 누적 온열질환 {prof['total_cases']}건 "
                       f"({prof['from_year']}~{prof['to_year']}, 시군구 단위 집계) 중 "
                       f"80세 이상 비중 {prof['ratio_80_plus']}%")

    return {
        "region_code": code,
        "region_name": region_label(r),
        "risk_score": round(final, 1),
        "risk_grade": ("매우 높음" if final >= 75 else "높음" if final >= 55
                       else "보통" if final >= 35 else "낮음"),
        "realtime": {
            "temperature_c": temp,
            "humidity_pct": hum,
            "feels_like_c": feels_like,
            "level": level,
            "announce_time": w.get("announce_time", "")
        },
        "static_breakdown": {
            "elderly": s["elderly_score"],
            "shelter": s["shelter_score"], "history": s["history_score"],
        },
        "illness_profile": prof,
        "reasons": reasons or ["특이 위험 요소 없음"],
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
    }


@mcp.tool()
def get_current_weather(region: str) -> dict:
    """특정 지역의 실시간 기상 실측 데이터(기온, 습도, 체감온도, 폭염 위험단계)를 반환한다.

    gyeongbuk_weather.csv 실측치 및 기상청 초단기실황 데이터를 기반으로 한다.

    Args:
        region: 행정표준코드 또는 지역명 (예: '포항시', '안동시 와룡면', '경산시 압량읍')
    """
    r = resolve_region(region)
    if not r:
        return {"error": f"'{region}' 지역을 찾을 수 없습니다."}

    w = get_weather_details(
        r["kma_nx"], r["kma_ny"],
        region_code=r["region_code"],
        sigungu=r["sigungu"],
        eupmyeondong=r["eupmyeondong"]
    )
    feels = w["feels_like"]
    lv = temp_to_level(feels)

    return {
        "region_code": r["region_code"],
        "region_name": region_label(r),
        "temperature_c": w["temperature"],
        "humidity_pct": w["humidity"],
        "feels_like_c": feels,
        "heat_risk_tier": lv,
        "announce_time": w.get("announce_time", ""),
        "grid_nx": r["kma_nx"],
        "grid_ny": r["kma_ny"],
    }


@mcp.tool()
def list_high_priority_regions(top_n: int = 10, level: str = "sigungu") -> dict:
    """오늘 우선 대응이 필요한 지역을 위험도 순으로 반환한다.

    Args:
        top_n: 반환할 지역 수 (기본 10)
        level: 'sigungu' 시군 단위 또는 'eupmyeondong' 읍면동 단위
    """
    rows = q(
        "SELECT r.region_code, r.sigungu, r.eupmyeondong, r.kma_nx, r.kma_ny, "
        "s.static_total FROM regions r JOIN static_risk_scores s "
        "ON r.region_code = s.region_code WHERE r.level = ? "
        "ORDER BY s.static_total DESC LIMIT ?", (level, max(top_n * 2, 20)))

    out = []
    for r in rows:
        feels = get_feels_like(r["kma_nx"], r["kma_ny"])
        lv = temp_to_level(feels)
        final = r["static_total"] * (1 - REALTIME_WEIGHT) + LEVEL_SCORE[lv] * REALTIME_WEIGHT
        out.append({
            "region_code": r["region_code"],
            "region_name": region_label(r),
            "risk_score": round(final, 1),
            "feels_like_c": feels,
            "level": lv,
        })

    out.sort(key=lambda x: -x["risk_score"])
    return {"as_of": datetime.now().isoformat(timespec="seconds"),
            "level": level, "regions": out[:top_n]}


@mcp.tool()
def get_shelter_coverage(region: str) -> dict:
    """지역의 무더위쉼터 접근성을 반환한다. 도보 5분(400m) 기준 사각지대 여부 포함.

    Args:
        region: 행정표준코드 또는 지역명
    """
    r = resolve_region(region)
    if not r:
        return {"error": f"'{region}' 지역을 찾을 수 없습니다."}
    rows = q("SELECT * FROM shelter_access WHERE region_code=?", (r["region_code"],))
    if not rows:
        return {"error": "쉼터 데이터 없음"}
    a = rows[0]
    return {
        "region_name": region_label(r),
        "shelter_count": a["shelter_count"],
        "within_400m_count": a["within_400m_count"],
        "nearest_distance_m": a["nearest_distance_m"],
        "is_blind_spot": bool(a["is_blind_spot"]),
        "note": "도보 5분(400m) 내 쉼터가 없으면 사각지대로 판정",
    }


@mcp.tool()
def get_vulnerable_population(region: str) -> dict:
    """지역의 취약인구 지표를 반환한다. 집계 통계이며 개인정보를 포함하지 않는다.

    Args:
        region: 행정표준코드 또는 지역명
    """
    r = resolve_region(region)
    if not r:
        return {"error": f"'{region}' 지역을 찾을 수 없습니다."}
    rows = q("SELECT * FROM vulnerability WHERE region_code=?", (r["region_code"],))
    if not rows:
        return {"error": "인구 데이터 없음"}
    v = rows[0]
    return {
        "region_name": region_label(r),
        "total_population": v["total_population"],
        "elderly_65_plus": v["elderly_65_plus"],
        "elderly_ratio_pct": round(v["elderly_ratio"] * 100, 1),
        "elderly_75_ratio_pct": round(v["elderly_75_ratio"] * 100, 1),
        "elderly_85_ratio_pct": round(v["elderly_85_ratio"] * 100, 1),
        "base_year": v["base_year"],
    }


def haversine_m(lat1, lon1, lat2, lon2):
    """두 좌표 간 거리(m)."""
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


@mcp.tool()
def get_nearby_shelters(region: str, radius_m: int = 1500, limit: int = 10) -> dict:
    """특정 지역 중심점 기준 반경 내에 위치한 실제 무더위쉼터 목록을 거리순으로 반환한다.

    각 쉼터의 정확한 위치(위도/경도), 주소, 이용가능인원, 냉방기기 대수,
    야간·휴일 운영 여부, 숙박 가능 여부, 카카오맵 지도 링크를 포함한다.

    Args:
        region: 행정표준코드 또는 지역명 (예: '포항시 구룡포읍', '의성군 안평면', '4711000100')
        radius_m: 검색 반경(미터 단위, 기본 1500m)
        limit: 최대 반환 쉼터 수 (기본 10개)
    """
    r = resolve_region(region)
    if not r:
        return {"error": f"'{region}' 지역을 찾을 수 없습니다."}

    lat, lon = r["lat"], r["lon"]
    sgg = r["sigungu"]

    # 동일 시군 및 인근 쉼터 조회
    shelters = q("SELECT * FROM shelters WHERE sigungu = ?", (sgg,))
    if not shelters:
        shelters = q("SELECT * FROM shelters")

    results = []
    for s in shelters:
        d = haversine_m(lat, lon, s["lat"], s["lon"])
        if d <= radius_m:
            results.append({
                "shelter_name": s["shelter_name"],
                "shelter_type": s["shelter_type"],
                "sigungu": s["sigungu"],
                "road_address": s["road_address"] or s["lot_address"],
                "distance_m": round(d, 1),
                "walking_minutes": round(d / 80.0, 1),  # 보행속도 분속 80m 기준
                "capacity": s["capacity"],
                "aircons": s["aircons"],
                "fans": s["fans"],
                "night_open": s["night_open"],
                "weekend_open": s["weekend_open"],
                "stay_open": s["stay_open"],
                "lat": s["lat"],
                "lon": s["lon"],
                "map_link": f"https://map.kakao.com/link/map/{s['shelter_name']},{s['lat']},{s['lon']}"
            })

    results.sort(key=lambda x: x["distance_m"])

    return {
        "region_name": region_label(r),
        "center_lat": lat,
        "center_lon": lon,
        "search_radius_m": radius_m,
        "total_found": len(results),
        "shelters": results[:limit]
    }


@mcp.tool()
def search_shelters(keyword: str, sigungu: str = None, limit: int = 20) -> dict:
    """쉼터명 또는 도로명/지번 주소 키워드로 경상북도 내 무더위쉼터 위치와 시설 정보를 검색한다.

    Args:
        keyword: 쉼터명 또는 주소 검색어 (예: '경로당', '행정복지센터', '흥해읍', '구룡포')
        sigungu: 특정 시군으로 한정할 경우 시군명 (예: '포항시', '안동시', '의성군')
        limit: 최대 반환 결과 수 (기본 20개)
    """
    params = [f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"]
    sgg_clause = ""
    if sigungu:
        sgg_clause = "AND sigungu LIKE ?"
        params.append(f"%{sigungu}%")

    sql = f"""
        SELECT * FROM shelters
        WHERE (shelter_name LIKE ? OR road_address LIKE ? OR lot_address LIKE ?)
        {sgg_clause}
        LIMIT ?
    """
    params.append(limit)
    rows = q(sql, tuple(params))

    out = []
    for s in rows:
        out.append({
            "shelter_name": s["shelter_name"],
            "shelter_type": s["shelter_type"],
            "sigungu": s["sigungu"],
            "road_address": s["road_address"] or s["lot_address"],
            "capacity": s["capacity"],
            "aircons": s["aircons"],
            "fans": s["fans"],
            "night_open": s["night_open"],
            "weekend_open": s["weekend_open"],
            "stay_open": s["stay_open"],
            "lat": s["lat"],
            "lon": s["lon"],
            "map_link": f"https://map.kakao.com/link/map/{s['shelter_name']},{s['lat']},{s['lon']}"
        })

    return {
        "keyword": keyword,
        "sigungu_filter": sigungu,
        "count": len(out),
        "shelters": out
    }


if __name__ == "__main__":
    mcp.run()
