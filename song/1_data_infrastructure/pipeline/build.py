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

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "hosu.db")
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
SCHEMA_PATH = os.path.join(BASE_DIR, "pipeline", "schema.sql")

WALK_5MIN_METERS = 400  # 도보 5분 기준 (국립재난안전연구원 분석 기준 차용)
SCORING_YEARS = 3       # 위험도 점수에 반영할 온열질환 최근 연도 수 (화면 표기는 전체 누적)
MAX_EMD_DISTANCE_KM = 60  # 읍면동 중심점이 소속 시군구에서 이보다 멀면 좌표 오류로 본다
                          # (경북 실측 정상 최대 29.5km, 발견된 오류는 147km)

# 정적 위험도 가중치 (합 1.0). 농업인 비율(0.25) 제거 후 나머지에 비례 재배분.
WEIGHTS = {
    "elderly": 0.47,   # 고령인구 비율 (초고령 쏠림 보정 포함, ELDERLY_SKEW_MAX_ADJ 참고)
    "shelter": 0.33,   # 쉼터 접근성 결핍
    "history": 0.20,   # 과거 온열질환 발생
}

# 고령인구 점수 = 65세 이상 비율(0~100)을 기준선으로 두고, 초고령 쏠림으로 ±보정.
#
# 폭염 초과사망 위험은 연령이 높을수록 급격히 커지므로(85세 이상 집단이 65~74세보다
# 훨씬 취약) 같은 고령화율이라도 고령층 내부가 더 고령인 지역을 더 위험하게 봐야 한다.
# 다만 65+/75+/85+ 비율을 직접 가중합하면 75+·85+가 항상 65+보다 작은 누적값이라
# 점수 스케일 자체가 구조적으로 내려앉는다 — 그래서 곱셈 보정 방식을 쓴다.
#
# 보정 강도는 경북 평균 대비 상대 편차이며 ±ELDERLY_SKEW_MAX_ADJ 안에서만 움직인다.
# 기준선(65+ 비율)이 유지되므로 등급 임계값과 근거 문구 임계값이 그대로 살아있다.
ELDERLY_SKEW_MAX_ADJ = 0.15


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
            f"{path} 없음. data/raw/에 원본 CSV를 먼저 넣으세요."
        )
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------- loaders
# 각 함수는 실제 공공데이터 API 호출로 교체 가능한 지점

def check_region_coords(regions):
    """읍면동 중심점이 소속 시군구에서 비상식적으로 멀면 경고한다.

    중심점이 틀리면 기상 격자·쉼터 거리·위험도가 전부 조용히 오염된다. 예외도 안 나고
    지도에서 엉뚱한 곳에 점 하나가 찍힐 뿐이라 제일 발견하기 어려운 종류의 오류다.
    (실제로 원본 중심점 데이터에서 포항시 상대1·2동이 147km 떨어진 좌표를 갖고 있었다.)

    시도별 경계를 하드코딩하지 않고 '부모 시군구로부터의 거리'로 판정하므로,
    다른 시도 데이터로 교체해도 그대로 동작한다. 경북 실측 정상 최대값은 29.5km다.
    """
    parents = {r["sigungu"]: r for r in regions if r["level"] == "sigungu"}
    suspects = []
    for r in regions:
        if r["level"] != "eupmyeondong":
            continue
        p = parents.get(r["sigungu"])
        if not p:
            continue
        d = haversine_m(p["lat"], p["lon"], r["lat"], r["lon"]) / 1000.0
        if d > MAX_EMD_DISTANCE_KM:
            suspects.append((d, r))

    for d, r in sorted(suspects, reverse=True):
        print(f"      경고: {r['sigungu']} {r['eupmyeondong']} 중심점이 시군구에서 "
              f"{d:.0f}km 떨어져 있음 ({r['lat']}, {r['lon']}) — 원본 좌표 확인 필요")
    return suspects


def load_regions():
    """행정구역 마스터. 실제로는 행정표준코드 + SGIS 경계 중심점."""
    rows = read_csv("regions.csv")
    out = []
    for r in rows:
        if r["level"] not in ("sigungu", "eupmyeondong"):
            continue  # 도(道) 전체 대표행 등은 분석 단위가 아니므로 제외 (schema.sql 계약과 일치)
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
    check_region_coords(out)
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
            "elderly_75_ratio": round(float(r["elderly_75_ratio"]) / 100.0, 4),
            "elderly_85_ratio": round(float(r["elderly_85_ratio"]) / 100.0, 4),
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


def age_group(age_raw):
    """나이(숫자) -> 10년 단위 연령대. 원본이 각세 나이라 버킷팅이 필요하다."""
    age = int(age_raw)
    if age < 10:
        return "10대 미만"
    if age >= 80:
        return "80대 이상"
    return f"{(age // 10) * 10}대"


def load_heat_illness(regions):
    """온열질환 발생 이력. 질병관리청 온열질환 감시데이터(개인 단위 원본,
    data/raw/heat_illness_gyeongbuk.csv)를 시군구 × 연도 × 연령대로 집계한다.

    원본이 시군구 단위까지만 주므로(읍면동 필드 없음) 여기서도 시군구 코드로만
    집계하고, 읍면동 스코어는 compute_static_scores에서 소속 시군구 값을 상속한다.

    연도 필터를 여기서 걸지 않고 전 기간을 적재한다 — 위험도 점수는 최근 3년만
    쓰지만(compute_static_scores), 화면 표기에는 전체 누적과 연령대 구성이 필요하다.
    한쪽 용도에 맞춰 미리 잘라내면 다른 쪽이 원본을 다시 읽어야 한다.
    """
    rows = read_csv("heat_illness_gyeongbuk.csv")
    code_by_sigungu = {r["sigungu"]: r["region_code"] for r in regions if r["level"] == "sigungu"}

    counts = {}
    skipped_no_sigungu = 0
    skipped_no_age = 0
    unmapped = set()
    for r in rows:
        date = r["발생일자"]
        if not date:
            continue
        sgg = r["발생시군구"].strip()
        if not sgg:
            skipped_no_sigungu += 1
            continue
        if not r["나이"].strip().isdigit():
            skipped_no_age += 1
            continue
        code = code_by_sigungu.get(sgg)
        if code is None:
            unmapped.add(sgg)
            continue
        key = (code, int(date[:4]), age_group(r["나이"]))
        counts[key] = counts.get(key, 0) + 1

    if unmapped:
        print(f"      경고: 시군구명 매핑 실패로 제외됨 - {sorted(unmapped)}")
    if skipped_no_sigungu:
        print(f"      발생시군구 미기재로 제외된 행: {skipped_no_sigungu}건")
    if skipped_no_age:
        print(f"      나이 미기재로 제외된 행: {skipped_no_age}건")

    return [
        # 원본에 사망 여부 필드가 없다. 0으로 채우면 "사망 0명"이라는 없는 사실을
        # 만들어내므로 미확인(NULL)으로 남긴다.
        {"region_code": code, "year": year, "age_group": ag,
         "case_count": n, "death_count": None}
        for (code, year, ag), n in sorted(counts.items())
    ]


def load_weather(regions):
    """gyeongbuk_weather.csv 기상 실측 데이터 로드 및 지역 매핑."""
    import sys
    _MCP_SERVER_DIR = os.path.join(BASE_DIR, "mcp_server")
    if _MCP_SERVER_DIR not in sys.path:
        sys.path.insert(0, _MCP_SERVER_DIR)
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

def _same_sigungu(region_sigungu, shelter_sigungu):
    """쉼터 데이터의 시군구명과 행정구역 시군구명을 맞춘다.

    쉼터 원본은 포항시를 구로 나누지 않아 '포항시'로 오는데, 행정구역은
    '포항시 남구'/'포항시 북구'로 갈린다. 접두 일치로 이 한 케이스를 흡수한다.
    """
    return (region_sigungu == shelter_sigungu
            or region_sigungu.startswith(shelter_sigungu + " ")
            or shelter_sigungu.startswith(region_sigungu + " "))


def assign_shelters_to_regions(regions, shelters):
    """각 쉼터를 소속 시군구 안에서 가장 가까운 읍면동에 배정해 관내 쉼터 수를 센다.

    읍면동 경계 데이터가 없으므로 '같은 시군구 + 최근접 중심점'으로 관내 여부를
    근사한다. 시군구는 원본에 실제로 있는 값이라, 경계를 통째로 추측하는 것보다
    훨씬 안전하다.

    중심점이 완전히 같은 행정동들(상대1동·상대2동·상대동 등 25개 그룹)은 물리적으로
    같은 위치이므로 접근성도 같다 — 한 곳만 골라 나머지를 0개로 만들면 실제로는 없는
    격차를 만들어내므로 동점은 모두에게 배정한다.
    """
    emd = [r for r in regions if r["level"] == "eupmyeondong"]
    counts = {r["region_code"]: 0 for r in regions}

    for s in shelters:
        cands = [r for r in emd if _same_sigungu(r["sigungu"], s["sigungu"])]
        if not cands:
            continue
        dists = [(haversine_m(r["lat"], r["lon"], s["lat"], s["lon"]), r) for r in cands]
        nearest = min(d for d, _ in dists)
        for d, r in dists:
            if d <= nearest + 1e-6:
                counts[r["region_code"]] += 1

    # 시군구 행은 관할 읍면동의 합으로 집계한다(자기 중심점 기준이 아니라).
    for r in regions:
        if r["level"] == "sigungu":
            counts[r["region_code"]] = sum(
                counts[e["region_code"]] for e in emd if e["sigungu"] == r["sigungu"]
            )
    return counts


def compute_shelter_access(regions, shelters):
    """관내 무더위쉼터 배치 현황과 중심점 기준 접근성을 계산한다.

    사각지대 = 관내에 지정된 쉼터가 없고, 이웃 마을 쉼터까지도 걸어갈 수 없는 곳.
    두 조건을 모두 봐야 한다.

    - 중심점 400m만 보면: 400m는 원래 '주민 집 → 쉼터' 거리인데 읍면동 중심점(몇 km
      범위의 기하학적 중심)에 적용돼, 마을이 잘 커버돼도 사각지대로 찍힌다(69% 해당).
    - 관내 배치만 보면: 도심 동은 촘촘해서 바로 옆 쉼터가 이웃 동에 배정된다.
      실제로 경주시 황오동은 288m 거리에 쉼터가 있는데도 관내 0개였다.

    걸어갈 수 있으면 행정구역이 달라도 사각지대가 아니다.
    within_400m_count는 '마을 중심에서 도보 5분 내'라는 별개 지표로 계속 제공한다.
    """
    now = datetime.now(timezone.utc).isoformat()
    counts = assign_shelters_to_regions(regions, shelters)

    # 원본 쉼터 목록에 아예 등장하지 않는 시군구는 '쉼터가 없다'가 아니라 '조사되지
    # 않았다'로 봐야 한다. 실제로 군위군은 2023년 대구광역시로 편입돼 경북 쉼터
    # 목록에서 빠졌을 뿐인데, 이를 사각지대로 단정하면 없는 사실을 만들어낸다.
    surveyed = {
        reg["sigungu"] for reg in regions
        if any(_same_sigungu(reg["sigungu"], s["sigungu"]) for s in shelters)
    }
    unsurveyed = {reg["sigungu"] for reg in regions} - surveyed
    if unsurveyed:
        print(f"      쉼터 데이터 없는 시군구(사각지대 판정 제외): {sorted(unsurveyed)}")

    out = []
    for reg in regions:
        # 최근접 거리는 시군구 경계를 넘어도 의미가 있다(이웃 마을 쉼터로 걸어갈 수 있음).
        dists = [haversine_m(reg["lat"], reg["lon"], s["lat"], s["lon"]) for s in shelters]
        nearest = min(dists) if dists else None
        in_region = counts[reg["region_code"]]
        walkable = nearest is not None and nearest <= WALK_5MIN_METERS
        blind = None if reg["sigungu"] in unsurveyed else int(in_region == 0 and not walkable)
        out.append({
            "region_code": reg["region_code"],
            "shelter_count": in_region,
            "within_400m_count": sum(1 for d in dists if d <= WALK_5MIN_METERS),
            "nearest_distance_m": round(nearest, 1) if nearest else None,
            "is_blind_spot": blind,
            "updated_at": now,
        })
    return out


def compute_static_scores(regions, vuln, access, illness):
    """각 위험 요소 점수(0~100) 산출 후 가중합."""
    now = datetime.now(timezone.utc).isoformat()
    vmap = {v["region_code"]: v for v in vuln}
    amap = {a["region_code"]: a for a in access}

    # 온열질환 이력: 최근 3년만 합산한다. 전 기간을 쓰면 10년 전 발생이 현재 위험도에
    # 그대로 반영돼, 최근 몇 해의 경향 변화를 못 따라간다. (화면 표기는 전체 누적을 쓴다)
    years = {row["year"] for row in illness}
    recent_years = set(sorted(years)[-SCORING_YEARS:]) if years else set()
    imap = {}
    for row in illness:
        if row["year"] not in recent_years:
            continue
        code = row["region_code"]
        imap[code] = imap.get(code, 0) + row["case_count"]

    # 정규화용 최댓값
    max_cases = max(imap.values()) if imap and max(imap.values()) > 0 else 1

    # 초고령 쏠림 보정의 기준선: 경북 전체 평균 85+/65+ 비중.
    # 절대값이 아니라 "이 지역이 경북 평균보다 더 늙었는가"라는 상대 비교라서,
    # 다른 시도 데이터로 교체해도 그 지역 평균에 맞춰 자동 재조정된다.
    skews = [v["elderly_85_ratio"] / v["elderly_ratio"]
             for v in vuln if v.get("elderly_ratio") and v.get("elderly_85_ratio") is not None]
    skew_baseline = sum(skews) / len(skews) if skews else 0.0

    out = []
    for reg in regions:
        code = reg["region_code"]
        v = vmap.get(code, {})
        a = amap.get(code, {})

        # 고령인구 점수: 65세 이상 비율을 기준선으로, 초고령(85+) 쏠림만큼 ±보정
        e65 = v.get("elderly_ratio") or 0.0
        e85 = v.get("elderly_85_ratio") or 0.0
        skew = (e85 / e65) if e65 else skew_baseline
        # 경북 평균 대비 상대 편차. ±100%로 잘라 이상치 한 곳이 점수를 뒤집지 않게 한다.
        rel = max(-1.0, min(1.0, (skew - skew_baseline) / skew_baseline)) if skew_baseline else 0.0
        es = min(100.0, e65 * 100.0 * (1 + ELDERLY_SKEW_MAX_ADJ * rel))

        # 쉼터 점수: 최근접 거리가 멀수록, 관내에 쉼터가 없을수록 높음.
        # 가산점 기준을 within_400m_count에서 관내 배치 여부로 바꿨다 — 중심점 400m
        # 기준은 읍면동의 69%가 해당돼 변별력이 없었다(compute_shelter_access 참고).
        dist = a.get("nearest_distance_m") or 2000.0
        ss = min(100.0, (dist / 2000.0) * 70.0
                 + (30.0 if a.get("is_blind_spot") else 0.0))

        # 과거 이력 점수. 원본이 시군구 단위까지만 있어 읍면동은 소속 시군구 값을 상속.
        cases = imap.get(code)
        if cases is None:
            cases = imap.get(code[:5] + "00000", 0)
        hs = (cases / max_cases) * 100.0

        total = (es * WEIGHTS["elderly"]
                 + ss * WEIGHTS["shelter"]
                 + hs * WEIGHTS["history"])

        out.append({
            "region_code": code,
            "elderly_score": round(es, 2),
            "shelter_score": round(ss, 2),
            "history_score": round(hs, 2),
            "static_total": round(total, 2),
            "computed_at": now,
        })
    return out


# ---------------------------------------------------------------- persist

def write_db(regions, vuln, access, illness, scores, shelters, weather):
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
        ":elderly_65_plus,:elderly_ratio,:elderly_75_ratio,:elderly_85_ratio,"
        ":base_year)", vuln)
    conn.executemany(
        "INSERT INTO shelter_access VALUES (:region_code,:shelter_count,"
        ":within_400m_count,:nearest_distance_m,:is_blind_spot,:updated_at)", access)
    conn.executemany(
        "INSERT INTO heat_illness_history VALUES (:region_code,:year,"
        ":age_group,:case_count,:death_count)", illness)
    conn.executemany(
        "INSERT INTO static_risk_scores VALUES (:region_code,:elderly_score,"
        ":shelter_score,:history_score,:static_total,:computed_at)", scores)

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
    blind = sum(1 for a in access if a["is_blind_spot"])
    print(f"      쉼터 {len(shelters)}곳 / 관내 쉼터 없고 도보권에도 없는 지역 {blind}곳")

    print("[4/6] 실시간 기상 실측 데이터 로드 (gyeongbuk_weather.csv)")
    weather = load_weather(regions)
    print(f"      기상 실측 {len(weather)}개 지역 매핑 완료")

    print("[5/6] 정적 위험도 스코어 계산")
    illness = load_heat_illness(regions)
    scores = compute_static_scores(regions, vuln, access, illness)

    print("[6/6] DB 저장")
    write_db(regions, vuln, access, illness, scores, shelters, weather)
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
