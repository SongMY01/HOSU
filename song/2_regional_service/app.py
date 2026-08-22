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


# ---------------------------------------------------------------- routes


@app.route("/")
def index():
    return send_from_directory(os.path.join(BASE_DIR, "static"), "index.html")


@app.route("/api/regions")
def api_regions():
    """모든 지역의 위험도·좌표·사각지대 정보를 반환."""
    level = request.args.get("level", "all")
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
               v.farmer_ratio, v.solitary_elderly,
               w.temperature, w.humidity, w.feels_like, w.risk_tier, w.announce_time
        FROM regions r
        LEFT JOIN static_risk_scores s  ON r.region_code = s.region_code
        LEFT JOIN shelter_access    sa ON r.region_code = sa.region_code
        LEFT JOIN vulnerability      v ON r.region_code = v.region_code
        LEFT JOIN realtime_weather   w ON r.region_code = w.region_code
        {where}
    """, params)

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

        reasons = []
        if LEVEL_SCORE.get(lv, 0) >= 66:
            reasons.append(f"체감온도 {feels:.1f}°C (기온 {r.get('temperature')}°C, 습도 {r.get('humidity')}%), {lv} 단계")
        if (r.get("elderly_score") or 0) >= 60:
            reasons.append(f"고령인구 비율 {(r.get('elderly_ratio') or 0)*100:.1f}%로 높음")
        if r.get("is_blind_spot"):
            reasons.append(f"도보 5분권 쉼터 없음 (최근접 {r.get('nearest_distance_m') or 0:.0f}m)")
        if (r.get("history_score") or 0) >= 60:
            reasons.append("과거 온열질환 발생 이력 상위권")
        r["reasons"] = reasons or ["특이 위험 요소 없음"]

    return jsonify({"as_of": datetime.now().isoformat(timespec="seconds"),
                    "count": len(rows), "regions": rows})


@app.route("/api/summary")
def api_summary():
    """대시보드 요약 통계."""
    total    = db("SELECT COUNT(*) c FROM regions")[0]["c"]
    sigungu  = db("SELECT COUNT(*) c FROM regions WHERE level='sigungu'")[0]["c"]
    blind    = db("SELECT COUNT(*) c FROM shelter_access WHERE is_blind_spot=1")[0]["c"]
    shelters = db("SELECT COUNT(*) c FROM shelters")[0]["c"]
    avg_r    = db("SELECT AVG(static_total) a FROM static_risk_scores")[0]["a"] or 0
    high     = db("SELECT COUNT(*) c FROM static_risk_scores WHERE static_total>=55")[0]["c"]

    return jsonify({
        "total_regions": total,
        "sigungu_count": sigungu,
        "shelter_blind_spots": blind,
        "shelters_total": shelters,
        "avg_static_risk": round(avg_r, 1),
        "high_risk_count": high,
    })


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
