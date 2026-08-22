"""
HOSU 배치 파이프라인
원본 공공데이터 -> 정규화 -> 정적 위험도 스코어 계산 -> SQLite 저장

실행: python pipeline/build.py
결과: data/hosu.db 생성

각 loader 함수는 실제 공공데이터 API로 교체 가능한 어댑터 구조.
API 키가 없는 환경에서는 data/raw/*.csv 샘플을 읽는다.
"""

import csv
import math
import os
import sqlite3
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "hosu.db")
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")

WALK_5MIN_METERS = 400  # 도보 5분 기준 (국립재난안전연구원 분석 기준 차용)

# 정적 위험도 가중치 (합 1.0)
WEIGHTS = {
    "elderly": 0.35,   # 고령인구 비율
    "farmer": 0.25,    # 농업인 비율 (야외노출)
    "shelter": 0.25,   # 쉼터 접근성 결핍
    "history": 0.15,   # 과거 온열질환 발생
}


# ---------------------------------------------------------------- helpers

def haversine_m(lat1, lon1, lat2, lon2):
    """두 좌표 간 거리(m). 쉼터 도보권 판정에 사용."""
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def latlon_to_kma_grid(lat, lon):
    """위경도 -> 기상청 동네예보 격자(nx, ny) 변환 (Lambert Conformal Conic)."""
    RE, GRID = 6371.00877, 5.0
    SLAT1, SLAT2, OLON, OLAT = 30.0, 60.0, 126.0, 38.0
    XO, YO = 43, 136

    DEGRAD = math.pi / 180.0
    re = RE / GRID
    slat1, slat2 = SLAT1 * DEGRAD, SLAT2 * DEGRAD
    olon, olat = OLON * DEGRAD, OLAT * DEGRAD

    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = (sf ** sn) * math.cos(slat1) / sn
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re * sf / (ro ** sn)

    ra = math.tan(math.pi * 0.25 + lat * DEGRAD * 0.5)
    ra = re * sf / (ra ** sn)
    theta = lon * DEGRAD - olon
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn

    nx = int(ra * math.sin(theta) + XO + 0.5)
    ny = int(ro - ra * math.cos(theta) + YO + 0.5)
    return nx, ny


def normalize(values):
    """min-max 정규화 -> 0~100. 전부 같은 값이면 50으로."""
    vals = [v for v in values if v is not None]
    if not vals:
        return {}
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return {i: 50.0 for i, _ in enumerate(values)}
    return {i: (v - lo) / (hi - lo) * 100 if v is not None else 0.0
            for i, v in enumerate(values)}


def read_csv(name):
    path = os.path.join(RAW_DIR, name)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} 없음. data/raw/에 원본 CSV를 넣거나 seed_sample.py를 먼저 실행하세요."
        )
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------- loaders
# 각 함수는 실제 공공데이터 API 호출로 교체 가능한 지점

def load_regions():
    """행정구역 마스터. 실제로는 행정표준코드 + SGIS 경계 중심점."""
    rows = read_csv("regions.csv")
    out = []
    for r in rows:
        lat, lon = float(r["lat"]), float(r["lon"])
        nx, ny = latlon_to_kma_grid(lat, lon)
        out.append({
            "region_code": r["region_code"],
            "sido": r["sido"],
            "sigungu": r["sigungu"],
            "eupmyeondong": r.get("eupmyeondong") or None,
            "level": r["level"],
            "lat": lat, "lon": lon,
            "kma_nx": nx, "kma_ny": ny,
        })
    return out


def load_vulnerability():
    """취약인구 지표. 실제로는 통계청 KOSIS / 주민등록 인구통계."""
    rows = read_csv("population.csv")
    out = []
    for r in rows:
        total = int(r["total_population"])
        elderly = int(r["elderly_65_plus"])
        out.append({
            "region_code": r["region_code"],
            "total_population": total,
            "elderly_65_plus": elderly,
            "elderly_ratio": round(elderly / total, 4) if total else 0.0,
            "farmer_ratio": float(r["farmer_ratio"]),
            "solitary_elderly": int(r["solitary_elderly"]),
            "base_year": int(r["base_year"]),
        })
    return out


def load_shelters():
    """무더위쉼터 좌표 및 시설 정보 (공공데이터포털/생활안전지도 실데이터)."""
    out = []
    for r in read_csv("shelters.csv"):
        try:
            area = float(r.get("area_m2") or 0.0)
        except ValueError:
            area = 0.0
        try:
            cap = int(float(r.get("capacity") or 0))
        except ValueError:
            cap = 0
        try:
            fans = int(float(r.get("fans") or 0))
        except ValueError:
            fans = 0
        try:
            acs = int(float(r.get("aircons") or 0))
        except ValueError:
            acs = 0

        out.append({
            "sigungu": r["sigungu"],
            "shelter_name": r.get("shelter_name") or "무더위쉼터",
            "shelter_type": r.get("shelter_type") or "-",
            "road_address": r.get("road_address") or "",
            "lot_address": r.get("lot_address") or "",
            "lat": float(r["lat"]),
            "lon": float(r["lon"]),
            "area_m2": area,
            "capacity": cap,
            "fans": fans,
            "aircons": acs,
            "night_open": r.get("night_open") or "-",
            "weekend_open": r.get("weekend_open") or "-",
            "stay_open": r.get("stay_open") or "-",
        })
    return out


def load_heat_illness():
    """온열질환 발생 이력. 실제로는 질병관리청 온열질환 감시체계."""
    return [
        {"region_code": r["region_code"], "year": int(r["year"]),
         "case_count": int(r["case_count"]), "death_count": int(r["death_count"])}
        for r in read_csv("heat_illness.csv")
    ]


def load_channel_coverage():
    """채널 커버리지. 생활지원사 관할/지킴이 순찰계획은 비공개 데이터이므로
    해커톤에서는 시뮬레이션 값 사용. 실제 도입 시 지자체 내부 데이터로 교체."""
    return [
        {"region_code": r["region_code"],
         "has_care_worker": int(r["has_care_worker"]),
         "has_village_guardian": int(r["has_village_guardian"]),
         "last_patrol_date": r["last_patrol_date"] or None}
        for r in read_csv("channel_coverage.csv")
    ]


def load_weather(regions):
    """gyeongbuk_weather.csv 기상 실측 데이터 로드 및 345개 지역 매핑."""
    from weather import get_weather_details

    weather_rows = []
    for r in regions:
        code = r["region_code"]
        sgg = r["sigungu"]
        emd = r["eupmyeondong"]
        nx, ny = r["kma_nx"], r["kma_ny"]

        w = get_weather_details(nx, ny, region_code=code, sigungu=sgg, eupmyeondong=emd)
        weather_rows.append({
            "region_code": code,
            "sigungu": sgg,
            "eupmyeondong": emd,
            "grid_nx": nx,
            "grid_ny": ny,
            "announce_time": w.get("announce_time", ""),
            "temperature": w.get("temperature", 28.0),
            "humidity": w.get("humidity", 70.0),
            "feels_like": w.get("feels_like", 29.0),
            "risk_tier": w.get("risk_tier", "관심"),
        })
    return weather_rows


# ---------------------------------------------------------------- compute

def compute_shelter_access(regions, shelters):
    """지역 중심점 기준 도보권(400m) 내 쉼터 수 계산."""
    now = datetime.now(timezone.utc).isoformat()
    out = []
    for reg in regions:
        dists = [
            haversine_m(reg["lat"], reg["lon"], s["lat"], s["lon"])
            for s in shelters
        ]
        count = len(dists)
        w400 = sum(1 for d in dists if d <= 400.0)
        nearest = min(dists) if dists else None
        out.append({
            "region_code": reg["region_code"],
            "shelter_count": count,
            "within_400m_count": w400,
            "nearest_distance_m": round(nearest, 1) if nearest else None,
            "is_blind_spot": 1 if w400 == 0 else 0,
            "updated_at": now,
        })
    return out


def compute_static_scores(regions, vuln, access, illness):
    """각 위험 요소 점수(0~100) 산출 후 가중합."""
    now = datetime.now(timezone.utc).isoformat()
    vmap = {v["region_code"]: v for v in vuln}
    amap = {a["region_code"]: a for a in access}

    # 온열질환 이력: 최근 3년 합산
    imap = {}
    for row in illness:
        code = row["region_code"]
        imap[code] = imap.get(code, 0) + row["case_count"]

    # 정규화용 최댓값
    max_cases = max(imap.values()) if imap and max(imap.values()) > 0 else 1

    out = []
    for reg in regions:
        code = reg["region_code"]
        v = vmap.get(code, {})
        a = amap.get(code, {})

        # 고령인구 점수: 고령화율(0~100) 그대로 사용
        es = (v.get("elderly_ratio") or 0.0) * 100.0

        # 농업인 점수: 농업인 비율(0~100)
        fs = (v.get("farmer_ratio") or 0.0) * 100.0

        # 쉼터 점수: 최근접 거리가 멀수록, 도보권 쉼터가 적을수록 높음
        dist = a.get("nearest_distance_m") or 2000.0
        w400 = a.get("within_400m_count") or 0
        ss = min(100.0, (dist / 2000.0) * 70.0 + (30.0 if w400 == 0 else 0.0))

        # 과거 이력 점수
        cases = imap.get(code, 0)
        hs = (cases / max_cases) * 100.0

        # 가중합
        total = (es * WEIGHTS["elderly"]
                 + fs * WEIGHTS["farmer"]
                 + ss * WEIGHTS["shelter"]
                 + hs * WEIGHTS["history"])

        out.append({
            "region_code": code,
            "elderly_score": round(es, 2),
            "farmer_score": round(fs, 2),
            "shelter_score": round(ss, 2),
            "history_score": round(hs, 2),
            "static_total": round(total, 2),
            "computed_at": now,
        })
    return out


# ---------------------------------------------------------------- persist

def write_db(regions, vuln, access, illness, scores, coverage, shelters, weather):
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())

    conn.executemany(
        "INSERT INTO regions VALUES (:region_code,:sido,:sigungu,:eupmyeondong,"
        ":level,:lat,:lon,:kma_nx,:kma_ny)", regions)
    conn.executemany(
        "INSERT INTO vulnerability VALUES (:region_code,:total_population,"
        ":elderly_65_plus,:elderly_ratio,:farmer_ratio,:solitary_elderly,:base_year)", vuln)
    conn.executemany(
        "INSERT INTO shelter_access VALUES (:region_code,:shelter_count,"
        ":within_400m_count,:nearest_distance_m,:is_blind_spot,:updated_at)", access)
    conn.executemany(
        "INSERT INTO heat_illness_history VALUES (:region_code,:year,"
        ":case_count,:death_count)", illness)
    conn.executemany(
        "INSERT INTO static_risk_scores VALUES (:region_code,:elderly_score,"
        ":farmer_score,:shelter_score,:history_score,:static_total,:computed_at)", scores)

    cov_rows = []
    for c in coverage:
        c = dict(c)
        c["is_uncovered"] = 0 if (c["has_care_worker"] or c["has_village_guardian"]) else 1
        cov_rows.append(c)
    conn.executemany(
        "INSERT INTO channel_coverage VALUES (:region_code,:has_care_worker,"
        ":has_village_guardian,:last_patrol_date,:is_uncovered)", cov_rows)

    conn.executemany(
        "INSERT INTO shelters (sigungu, shelter_name, shelter_type, road_address, lot_address, "
        "lat, lon, area_m2, capacity, fans, aircons, night_open, weekend_open, stay_open) "
        "VALUES (:sigungu, :shelter_name, :shelter_type, :road_address, :lot_address, "
        ":lat, :lon, :area_m2, :capacity, :fans, :aircons, :night_open, :weekend_open, :stay_open)",
        shelters
    )

    conn.executemany(
        "INSERT INTO realtime_weather (region_code, sigungu, eupmyeondong, grid_nx, grid_ny, "
        "announce_time, temperature, humidity, feels_like, risk_tier) "
        "VALUES (:region_code, :sigungu, :eupmyeondong, :grid_nx, :grid_ny, "
        ":announce_time, :temperature, :humidity, :feels_like, :risk_tier)",
        weather
    )

    conn.commit()
    conn.close()


def main():
    print("[1/6] 행정구역 로드 및 기상청 격자 매핑")
    regions = load_regions()
    print(f"      {len(regions)}개 지역")

    print("[2/6] 취약인구 지표 로드")
    vuln = load_vulnerability()

    print("[3/6] 쉼터 도보권 접근성 계산")
    shelters = load_shelters()
    access = compute_shelter_access(regions, shelters)
    blind = sum(a["is_blind_spot"] for a in access)
    print(f"      쉼터 {len(shelters)}곳 / 도보권 사각지대 {blind}개 지역")

    print("[4/6] 실시간 기상 실측 데이터 로드 (gyeongbuk_weather.csv)")
    weather = load_weather(regions)
    print(f"      기상 실측 {len(weather)}개 지역 매핑 완료")

    print("[5/6] 정적 위험도 스코어 계산")
    illness = load_heat_illness()
    scores = compute_static_scores(regions, vuln, access, illness)

    print("[6/6] DB 저장")
    coverage = load_channel_coverage()
    write_db(regions, vuln, access, illness, scores, coverage, shelters, weather)
    print(f"      완료 -> {DB_PATH}")

    top = sorted(scores, key=lambda s: -s["static_total"])[:5]
    rmap = {r["region_code"]: r for r in regions}
    print("\n정적 위험도 상위 5개 지역:")
    for s in top:
        r = rmap[s["region_code"]]
        name = r["eupmyeondong"] or r["sigungu"]
        print(f"  {s['static_total']:6.2f}  {r['sigungu']} {name}")


if __name__ == "__main__":
    main()
