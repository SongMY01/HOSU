"""
경상북도 읍면동별 연령별(각세) 인구현황 정제 및 나이대별 비율 가공 스크립트

입력: test/2. 읍면동 연령별(각세) 인구현황-표 1.csv
출력: data/raw/population_eupmyeondong_age_ratio.csv

산출 지표:
- 총인구수 (total_population)
- 65세 이상 고령자 수 및 비율 (elderly_65_plus, elderly_65_ratio)
- 75세 이상 후기 고령자 수 및 비율 (elderly_75_plus, elderly_75_ratio)
- 85세 이상 초고령자 수 및 비율 (elderly_85_plus, elderly_85_ratio)
- 생애주기별 인구/비율 (0~14세 유소년, 15~64세 생산가능, 65세+ 고령)
- 노령화지수 (aging_index)
- 10세 구간별 인구 및 비율 (0~9세, 10~19세, ..., 80세 이상)
"""

import csv
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_PATH = os.path.join(BASE_DIR, "test", "2. 읍면동 연령별(각세) 인구현황-표 1.csv")
DST_PATH = os.path.join(BASE_DIR, "data", "raw", "population_eupmyeondong_age_ratio.csv")

GYEONGBUK_SIGUNGU = [
    "포항시", "경주시", "김천시", "안동시", "구미시", "영주시", "영천시", "상주시", "문경시", "경산시",
    "군위군", "의성군", "청송군", "영양군", "영덕군", "청도군", "고령군", "성주군", "칠곡군", "예천군",
    "봉화군", "울진군", "울릉군"
]


def clean_int(val: str) -> int:
    if not val:
        return 0
    s = val.replace(",", "").replace(" ", "").replace("\t", "").replace('"', "").strip()
    return int(s) if s else 0


def process_population_data():
    rows_out = []

    with open(SRC_PATH, encoding="utf-8") as f:
        # 상단 표 제목/공백 4줄 건너뛰기
        for _ in range(4):
            f.readline()
        reader = csv.reader(f)
        header = next(reader)

        current_sido = "경상북도"
        current_sigungu = ""
        current_gu = ""

        for r in reader:
            if not r or not r[0].strip():
                continue
            name = r[0].strip()

            if name == "경상북도":
                level = "sido"
                current_sigungu = ""
                current_gu = ""
                sgg_name = ""
                gu_name = ""
                emd_name = ""
            elif name in GYEONGBUK_SIGUNGU:
                level = "sigungu"
                current_sigungu = name
                current_gu = ""
                sgg_name = name
                gu_name = ""
                emd_name = ""
            elif name in ["남구", "북구"]:
                level = "gu"
                current_gu = name
                sgg_name = current_sigungu
                gu_name = name
                emd_name = ""
            else:
                level = "eupmyeondong"
                sgg_name = current_sigungu
                gu_name = current_gu
                emd_name = name

            ages = [clean_int(x) for x in r[1:102]]
            total = sum(ages)
            if total == 0:
                continue

            p65 = sum(ages[65:])
            p75 = sum(ages[75:])
            p85 = sum(ages[85:])

            c0_14 = sum(ages[0:15])
            w15_64 = sum(ages[15:65])

            p0_9 = sum(ages[0:10])
            p10_19 = sum(ages[10:20])
            p20_29 = sum(ages[20:30])
            p30_39 = sum(ages[30:40])
            p40_49 = sum(ages[40:50])
            p50_59 = sum(ages[50:60])
            p60_69 = sum(ages[60:70])
            p70_79 = sum(ages[70:80])
            p80_plus = sum(ages[80:])

            aging_idx = round((p65 / c0_14 * 100), 1) if c0_14 > 0 else 0.0

            rows_out.append({
                "sido": current_sido,
                "sigungu": sgg_name,
                "gu": gu_name,
                "eupmyeondong": emd_name,
                "level": level,
                "region_name": name,
                "total_population": total,

                # 고령자 지표
                "elderly_65_plus": p65,
                "elderly_65_ratio": round(p65 / total * 100, 2),
                "elderly_75_plus": p75,
                "elderly_75_ratio": round(p75 / total * 100, 2),
                "elderly_85_plus": p85,
                "elderly_85_ratio": round(p85 / total * 100, 2),

                # 생애주기별
                "child_0_14": c0_14,
                "child_0_14_ratio": round(c0_14 / total * 100, 2),
                "working_15_64": w15_64,
                "working_15_64_ratio": round(w15_64 / total * 100, 2),
                "aging_index": aging_idx,

                # 10세 구간별 인구수 및 비율
                "pop_0_9": p0_9,
                "ratio_0_9": round(p0_9 / total * 100, 2),
                "pop_10_19": p10_19,
                "ratio_10_19": round(p10_19 / total * 100, 2),
                "pop_20_29": p20_29,
                "ratio_20_29": round(p20_29 / total * 100, 2),
                "pop_30_39": p30_39,
                "ratio_30_39": round(p30_39 / total * 100, 2),
                "pop_40_49": p40_49,
                "ratio_40_49": round(p40_49 / total * 100, 2),
                "pop_50_59": p50_59,
                "ratio_50_59": round(p50_59 / total * 100, 2),
                "pop_60_69": p60_69,
                "ratio_60_69": round(p60_69 / total * 100, 2),
                "pop_70_79": p70_79,
                "ratio_70_79": round(p70_79 / total * 100, 2),
                "pop_80_plus": p80_plus,
                "ratio_80_plus": round(p80_plus / total * 100, 2),
            })

    fieldnames = list(rows_out[0].keys())

    os.makedirs(os.path.dirname(DST_PATH), exist_ok=True)
    with open(DST_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_out)

    print(f"가공 완료: 총 {len(rows_out)}개 행 저장 -> {DST_PATH}")


if __name__ == "__main__":
    process_population_data()
