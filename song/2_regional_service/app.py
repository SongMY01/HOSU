"""
HOSU TF 대시보드 서버
경상북도 폭염 위험도를 지도 위에 시각화하고 사각지대를 표시하는 웹 대시보드.

실행: python3 dashboard.py
접속: http://localhost:5000
사전 조건: python3 build.py 로 data/hosu.db 생성
"""

import os
import sys
import sqlite3
from datetime import datetime

from flask import Flask, jsonify, send_from_directory, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
INFRA_DIR = os.path.join(ROOT_DIR, "1_data_infrastructure")

# mcp_server 모듈(weather) 참조
sys.path.insert(0, os.path.join(INFRA_DIR, "mcp_server"))
from weather import get_feels_like, temp_to_level, LEVEL_SCORE

sys.path.insert(0, BASE_DIR)
import briefing

app = Flask(__name__, static_folder=os.path.join(BASE_DIR, "static"))

DB_PATH = os.path.join(INFRA_DIR, "data", "hosu.db")
REALTIME_WEIGHT = 0.4


def db(sql, params=()):
    """SQLite read-only 조회."""
    if not os.path.exists(DB_PATH):
        raise RuntimeError(f"{DB_PATH} 없음. `python 1_data_infrastructure/pipeline/build.py` 를 먼저 실행하세요.")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def region_label(r):
    return f"{r['sigungu']} {r['eupmyeondong']}" if r.get("eupmyeondong") else r["sigungu"]


def illness_profiles():
    """시군구별 온열질환 누적 프로파일. {시군구코드: {총건수, 80대이상, 비중, 연도범위}}

    위험도 점수는 최근 3년만 쓰지만(build.py), 화면에는 전체 누적과 연령 구성을 보여준다 —
    "왜 위험한가"를 설명할 때 표본이 클수록 근거가 단단하기 때문이다.
    연도 범위를 함께 반환해 실제 집계 기간을 화면에 정직하게 표기한다.
    """
    rows = db("""
        SELECT region_code,
               SUM(case_count) AS total,
               SUM(CASE WHEN age_group = '80대 이상' THEN case_count ELSE 0 END) AS elderly_cases,
               MIN(year) AS from_year, MAX(year) AS to_year
        FROM heat_illness_history GROUP BY region_code
    """)
    out = {}
    for r in rows:
        total = r["total"] or 0
        out[r["region_code"]] = {
            "total_cases": total,
            "cases_80_plus": r["elderly_cases"] or 0,
            "ratio_80_plus": round((r["elderly_cases"] or 0) / total * 100, 1) if total else 0.0,
            "from_year": r["from_year"],
            "to_year": r["to_year"],
        }
    return out


# ---------------------------------------------------------------- routes


@app.route("/")
def index():
    return send_from_directory(os.path.join(BASE_DIR, "static"), "index.html")


def load_regions(level="all"):
    """지역별 위험도·좌표·사각지대 정보를 계산해 반환.

    /api/regions 와 AI 브리핑이 같은 값을 쓰도록 여기 한 곳에서만 계산한다 —
    최종 위험도 산식이 두 벌로 갈라지면 화면과 브리핑이 다른 숫자를 말하게 된다.
    """
    where, params = "", ()
    if level != "all":
        where = "WHERE r.level = ?"
        params = (level,)

    rows = db(f"""
        SELECT r.region_code, r.sigungu, r.eupmyeondong, r.level,
               r.lat, r.lon, r.kma_nx, r.kma_ny,
               s.static_total, s.elderly_score,
               s.shelter_score, s.history_score,
               sa.shelter_count, sa.within_400m_count,
               sa.nearest_distance_m, sa.is_blind_spot,
               v.total_population, v.elderly_65_plus, v.elderly_ratio,
               v.elderly_75_ratio, v.elderly_85_ratio, v.base_year,
               w.temperature, w.humidity, w.feels_like, w.risk_tier, w.announce_time
        FROM regions r
        LEFT JOIN static_risk_scores s  ON r.region_code = s.region_code
        LEFT JOIN shelter_access    sa ON r.region_code = sa.region_code
        LEFT JOIN vulnerability      v ON r.region_code = v.region_code
        LEFT JOIN realtime_weather   w ON r.region_code = w.region_code
        {where}
    """, params)

    profiles = illness_profiles()

    for r in rows:
        r["region_name"] = region_label(r)
        st = r.get("static_total") or 0
        feels = r.get("feels_like")
        if feels is None:
            feels = get_feels_like(r["kma_nx"], r["kma_ny"])
        
        lv = r.get("risk_tier") or temp_to_level(feels)
        rt = LEVEL_SCORE.get(lv, 20.0)
        final = round(st * (1 - REALTIME_WEIGHT) + rt * REALTIME_WEIGHT, 1)

        r["final_risk"] = final
        r["risk_grade"] = ("매우 높음" if final >= 75 else "높음" if final >= 55
                           else "보통" if final >= 35 else "낮음")
        r["feels_like_c"] = round(feels, 1)
        r["temperature_c"] = r.get("temperature")
        r["humidity_pct"] = r.get("humidity")
        r["temp_level"] = lv

        # 판단 근거. 수치와 그 산출 근거를 함께 적는다 — 담당자가 검증할 수 없는
        # 판단은 현장에서 쓰이지 않으므로, 결론만이 아니라 계산에 쓴 값을 같이 보여준다.
        prof = profiles.get((r["region_code"][:5] + "00000"))  # 이력은 시군구 단위
        r["illness_profile"] = prof

        reasons = []
        if LEVEL_SCORE.get(lv, 0) >= 66:
            reasons.append(
                f"체감온도 {feels:.1f}°C — {lv} 단계 기준 초과 "
                f"(실측 기온 {r.get('temperature')}°C, 습도 {r.get('humidity')}%로 계산)"
            )
        if (r.get("elderly_score") or 0) >= 60:
            basis = f" ({r['base_year']}년 기준)" if r.get("base_year") else ""
            reasons.append(
                f"65세 이상 인구비율 {(r.get('elderly_ratio') or 0)*100:.1f}%{basis}"
            )
        if r.get("is_blind_spot"):
            reasons.append(
                f"가장 가까운 무더위쉼터가 {r.get('nearest_distance_m') or 0:.0f}m "
                f"(도보 {(r.get('nearest_distance_m') or 0)/80:.0f}분) — 도보권 밖"
            )
        if prof and prof["total_cases"] and (r.get("history_score") or 0) >= 60:
            reasons.append(
                f"{r['sigungu']} 누적 온열질환 {prof['total_cases']}건 "
                f"({prof['from_year']}~{prof['to_year']}, 시군구 단위 집계) 중 "
                f"80세 이상 비중 {prof['ratio_80_plus']}%"
            )
        r["reasons"] = reasons or ["특이 위험 요소 없음"]

    return rows


@app.route("/api/regions")
def api_regions():
    """모든 지역의 위험도·좌표·사각지대 정보를 반환."""
    rows = load_regions(request.args.get("level", "all"))
    return jsonify({"as_of": datetime.now().isoformat(timespec="seconds"),
                    "count": len(rows), "regions": rows})


def summary_stats():
    """대시보드 요약 통계. /api/summary 와 AI 브리핑이 공유한다."""
    total    = db("SELECT COUNT(*) c FROM regions")[0]["c"]
    sigungu  = db("SELECT COUNT(*) c FROM regions WHERE level='sigungu'")[0]["c"]
    blind    = db("SELECT COUNT(*) c FROM shelter_access WHERE is_blind_spot=1")[0]["c"]
    shelters = db("SELECT COUNT(*) c FROM shelters")[0]["c"]
    avg_r    = db("SELECT AVG(static_total) a FROM static_risk_scores")[0]["a"] or 0
    high     = db("SELECT COUNT(*) c FROM static_risk_scores WHERE static_total>=55")[0]["c"]

    return {
        "total_regions": total,
        "sigungu_count": sigungu,
        "shelter_blind_spots": blind,
        "shelters_total": shelters,
        "avg_static_risk": round(avg_r, 1),
        "high_risk_count": high,
    }


@app.route("/api/summary")
def api_summary():
    return jsonify(summary_stats())


@app.route("/api/briefing")
def api_briefing():
    """오늘의 AI 상황 브리핑. 키가 없거나 호출이 실패하면 규칙 기반 문장으로 degrade한다."""
    result = briefing.generate(load_regions("all"), summary_stats())
    return jsonify({"as_of": datetime.now().isoformat(timespec="seconds"), **result})


@app.route("/api/shelters")
def api_shelters():
    """무더위쉼터 위치 목록 및 상세 정보 반환."""
    sigungu = request.args.get("sigungu")
    keyword = request.args.get("q")
    limit = int(request.args.get("limit", 500))

    where_clauses = []
    params = []

    if sigungu:
        where_clauses.append("sigungu = ?")
        params.append(sigungu)
    if keyword:
        where_clauses.append("(shelter_name LIKE ? OR road_address LIKE ? OR lot_address LIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    params.append(limit)

    rows = db(f"""
        SELECT id, sigungu, shelter_name, shelter_type, road_address, lot_address,
               lat, lon, area_m2, capacity, fans, aircons, night_open, weekend_open, stay_open
        FROM shelters
        {where_sql}
        LIMIT ?
    """, tuple(params))

    return jsonify({
        "count": len(rows),
        "shelters": rows
    })


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print(f"⚠  {DB_PATH} 없음. 먼저 `python 1_data_infrastructure/pipeline/build.py`를 실행하세요.")
        exit(1)
    print("🔥 HOSU 대시보드: http://localhost:5050")
    app.run(debug=True, port=5050, host="0.0.0.0")
