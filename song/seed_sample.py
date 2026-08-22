"""
샘플 원본 데이터 생성기 (data/raw/*.csv)

실제 공공데이터 API 키를 받기 전까지 파이프라인을 돌려보기 위한 seed.
지역명/좌표/행정코드는 실제 경북 22개 시군 값이며,
인구·농업인비율·온열질환 건수는 공개 보도 수치를 참고한 근사치다.

실행: python pipeline/seed_sample.py
"""

import csv
import os
import random

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")

random.seed(20260822)

# 경북 22개 시군 (region_code, 시군명, 위도, 경도, 총인구 근사, 고령비율 근사, 농업인비율 근사)
SIGUNGU = [
    ("47110", "포항시", 36.0190, 129.3435, 493000, 0.24, 0.06),
    ("47130", "경주시", 35.8562, 129.2247, 248000, 0.29, 0.14),
    ("47150", "김천시", 36.1398, 128.1136, 137000, 0.28, 0.18),
    ("47170", "안동시", 36.5684, 128.7294, 152000, 0.31, 0.19),
    ("47190", "구미시", 36.1196, 128.3441, 405000, 0.16, 0.05),
    ("47210", "영주시", 36.8057, 128.6240, 100000, 0.33, 0.22),
    ("47230", "영천시", 35.9733, 128.9386, 100000, 0.34, 0.24),
    ("47250", "상주시", 36.4109, 128.1590, 94000, 0.36, 0.28),
    ("47280", "문경시", 36.5867, 128.1867, 68000, 0.37, 0.24),
    ("47290", "경산시", 35.8251, 128.7414, 262000, 0.21, 0.07),
    ("47720", "의성군", 36.3527, 128.6971, 49000, 0.45, 0.36),
    ("47730", "청송군", 36.4362, 129.0570, 23000, 0.42, 0.34),
    ("47750", "영양군", 36.6667, 129.1124, 15000, 0.43, 0.35),
    ("47760", "영덕군", 36.4150, 129.3656, 34000, 0.40, 0.28),
    ("47770", "청도군", 35.6473, 128.7341, 41000, 0.41, 0.32),
    ("47820", "고령군", 35.7262, 128.2627, 30000, 0.38, 0.30),
    ("47830", "성주군", 35.9190, 128.2830, 42000, 0.37, 0.33),
    ("47840", "칠곡군", 35.9955, 128.4017, 110000, 0.24, 0.12),
    ("47850", "예천군", 36.6577, 128.4527, 55000, 0.38, 0.29),
    ("47900", "봉화군", 36.8930, 128.7325, 30000, 0.43, 0.31),
    ("47920", "울진군", 36.9930, 129.4004, 47000, 0.36, 0.24),
    ("47930", "울릉군", 37.4845, 130.9057, 9000, 0.32, 0.18),
]

# 공개 보도 기반 2026년 온열질환자 수 (일부 실측, 나머지는 규모 비례 근사)
KNOWN_CASES = {
    "47110": 58, "47190": 29, "47170": 26, "47150": 19, "47130": 16, "47750": 0,
}


def write(name, fieldnames, rows):
    os.makedirs(RAW_DIR, exist_ok=True)
    path = os.path.join(RAW_DIR, name)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"  {name}  ({len(rows)} rows)")


def main():
    print("샘플 원본 데이터 생성:")

    # 1. regions.csv — 시군 단위 + 각 시군당 읍면동 3개씩 가상 생성
    regions = []
    for code, name, lat, lon, *_ in SIGUNGU:
        regions.append({
            "region_code": code + "00000", "sido": "경상북도", "sigungu": name,
            "eupmyeondong": "", "level": "sigungu",
            "lat": lat, "lon": lon,
        })
        for i in range(1, 4):
            regions.append({
                "region_code": f"{code}{i:05d}", "sido": "경상북도", "sigungu": name,
                "eupmyeondong": f"{name[:-1]}{i}면", "level": "eupmyeondong",
                "lat": round(lat + random.uniform(-0.12, 0.12), 5),
                "lon": round(lon + random.uniform(-0.12, 0.12), 5),
            })
    write("regions.csv",
          ["region_code", "sido", "sigungu", "eupmyeondong", "level", "lat", "lon"],
          regions)

    # 2. population.csv
    pop = []
    for code, name, lat, lon, total, eratio, framer in SIGUNGU:
        units = [(code + "00000", total)] + [
            (f"{code}{i:05d}", int(total * random.uniform(0.05, 0.15))) for i in range(1, 4)
        ]
        for rc, t in units:
            er = min(0.75, eratio * random.uniform(0.9, 1.35))
            pop.append({
                "region_code": rc, "total_population": t,
                "elderly_65_plus": int(t * er),
                "farmer_ratio": round(min(0.9, framer * random.uniform(0.8, 1.6)), 4),
                "solitary_elderly": int(t * er * random.uniform(0.15, 0.32)),
                "base_year": 2025,
            })
    write("population.csv",
          ["region_code", "total_population", "elderly_65_plus", "farmer_ratio",
           "solitary_elderly", "base_year"], pop)

    # 3. shelters.csv — 인구 규모에 비례해 쉼터 배치 (도시 밀집, 농촌 희소)
    shelters = []
    for code, name, lat, lon, total, eratio, _ in SIGUNGU:
        n = max(3, int(total / 6000))
        spread = 0.05 if total > 200000 else 0.20  # 농촌일수록 넓게 흩어짐
        for _ in range(n):
            shelters.append({
                "sigungu": name,
                "lat": round(lat + random.uniform(-spread, spread), 5),
                "lon": round(lon + random.uniform(-spread, spread), 5),
            })
    write("shelters.csv", ["sigungu", "lat", "lon"], shelters)

    # 4. heat_illness.csv
    illness = []
    for code, name, lat, lon, total, eratio, _ in SIGUNGU:
        base = KNOWN_CASES.get(code, max(0, int(total / 9000 * (1 + eratio))))
        for year, mult in [(2024, 0.7), (2025, 0.9), (2026, 1.0)]:
            c = int(base * mult)
            illness.append({
                "region_code": code + "00000", "year": year,
                "case_count": c,
                "death_count": 1 if (c > 40 and year == 2026) else 0,
            })
    write("heat_illness.csv",
          ["region_code", "year", "case_count", "death_count"], illness)

    # 5. channel_coverage.csv — 실제로는 지자체 내부 데이터, 여기선 시뮬레이션
    cov = []
    for r in regions:
        is_city = r["level"] == "sigungu"
        care = 1 if is_city else random.choices([1, 0], weights=[0.35, 0.65])[0]
        guard = random.choices([1, 0], weights=[0.7, 0.3])[0] if not is_city else random.choices([1, 0], weights=[0.7, 0.3])[0]
        days_ago = random.randint(0, 9)
        cov.append({
            "region_code": r["region_code"],
            "has_care_worker": care,
            "has_village_guardian": guard,
            "last_patrol_date": f"2026-08-{max(1, 22 - days_ago):02d}" if guard else "",
        })
    write("channel_coverage.csv",
          ["region_code", "has_care_worker", "has_village_guardian",
           "last_patrol_date"], cov)

    print("\n완료. 이제 `python pipeline/build.py` 를 실행하세요.")


if __name__ == "__main__":
    main()
