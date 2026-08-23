"""파이프라인 집계 로직 회귀 테스트. 프레임워크 없이 assert만 사용한다.

실행: python 1_data_infrastructure/pipeline/test_build.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build as B


def test_heat_illness_maps_all_sigungu():
    """heat_illness_gyeongbuk.csv의 발생시군구명이 regions.csv 시군구명과 전부 매핑돼야 한다.
    안 그러면 실제 이력 건수가 조용히 빠진 채로 위험도가 계산된다."""
    regions = B.load_regions()
    rows = B.read_csv("heat_illness_gyeongbuk.csv")
    code_by_sigungu = {r["sigungu"]: r["region_code"] for r in regions if r["level"] == "sigungu"}

    years_present = sorted({r["발생일자"][:4] for r in rows if r["발생일자"]})
    recent_years = set(years_present[-3:])

    unmapped = set()
    for r in rows:
        date = r["발생일자"]
        sgg = r["발생시군구"].strip()
        if date and date[:4] in recent_years and sgg and sgg not in code_by_sigungu:
            unmapped.add(sgg)

    assert not unmapped, f"매핑 실패한 시군구명: {sorted(unmapped)}"


def test_eupmyeondong_inherits_sigungu_history():
    """읍면동 지역은 자기 시군구와 동일한 history_score를 가져야 한다(상속 로직 회귀 방지)."""
    regions = B.load_regions()
    vuln = B.load_vulnerability()
    shelters = B.load_shelters()
    access = B.compute_shelter_access(regions, shelters)
    illness = B.load_heat_illness(regions)
    scores = {s["region_code"]: s for s in B.compute_static_scores(regions, vuln, access, illness)}

    sample = next(r for r in regions if r["level"] == "eupmyeondong" and r["sigungu"] == "의성군")
    parent_code = sample["region_code"][:5] + "00000"

    assert scores[sample["region_code"]]["history_score"] == scores[parent_code]["history_score"]


def _all_scores():
    regions = B.load_regions()
    vuln = B.load_vulnerability()
    shelters = B.load_shelters()
    access = B.compute_shelter_access(regions, shelters)
    illness = B.load_heat_illness(regions)
    scores = {s["region_code"]: s for s in B.compute_static_scores(regions, vuln, access, illness)}
    return scores, {v["region_code"]: v for v in vuln}


def test_elderly_score_applies_skew_within_bounds():
    """초고령 쏠림 보정이 실제로 적용되되, 기준선(65+ 비율) 대비 ±MAX_ADJ를 넘지 않아야 한다.
    보정이 이 범위를 넘으면 등급·근거 문구 임계값이 의미를 잃는다."""
    scores, vmap = _all_scores()
    adj = B.ELDERLY_SKEW_MAX_ADJ

    differs = False
    for code, s in scores.items():
        es = s["elderly_score"]
        assert 0.0 <= es <= 100.0, f"{code}: elderly_score 범위 벗어남 {es}"

        base = (vmap.get(code, {}).get("elderly_ratio") or 0.0) * 100.0
        assert base * (1 - adj) - 0.01 <= es <= base * (1 + adj) + 0.01, \
            f"{code}: 보정폭이 ±{adj:.0%}를 벗어남 (base={base:.2f}, es={es:.2f})"
        if abs(es - base) > 0.01:
            differs = True
    assert differs, "elderly_score가 65+ 단일 비율과 항상 같음 - 쏠림 보정이 반영 안 됐을 수 있음"


def test_elderly_score_scale_preserved():
    """기준선 스케일이 살아있어야 근거 문구 임계값(60)이 실제로 발동한다.
    누적비율 직접 가중합 방식으로 되돌아가면 최댓값이 40 아래로 주저앉아 이 테스트가 깨진다."""
    scores, _ = _all_scores()
    over_60 = [c for c, s in scores.items() if s["elderly_score"] >= 60]
    assert over_60, "elderly_score >= 60인 지역이 없음 - '고령인구 비율 높음' 근거가 영영 안 뜬다"


def test_scoring_uses_recent_years_only():
    """위험도 점수는 최근 3년만 반영해야 한다. 전 기간이 섞이면 오래된 발생이
    현재 위험도를 좌우한다(화면 표기용 전체 누적과 혼동하기 쉬운 지점)."""
    regions = B.load_regions()
    illness = B.load_heat_illness(regions)
    years = sorted({row["year"] for row in illness})

    assert len(years) > B.SCORING_YEARS, "전 기간이 적재되지 않았다면 이 구분 자체가 무의미"

    scores = {s["region_code"]: s for s in B.compute_static_scores(
        regions, B.load_vulnerability(),
        B.compute_shelter_access(regions, B.load_shelters()), illness)}

    # 최근 3년 밖 데이터만 있는 지역은 이력 점수가 0이어야 한다.
    recent = set(years[-B.SCORING_YEARS:])
    by_code = {}
    for row in illness:
        by_code.setdefault(row["region_code"], set()).add(row["year"])
    old_only = [c for c, ys in by_code.items() if not (ys & recent)]
    for code in old_only:
        assert scores[code]["history_score"] == 0, f"{code}: 최근 3년 밖인데 점수가 붙음"


def test_region_coords_within_parent_sigungu():
    """모든 읍면동 중심점이 소속 시군구 근처에 있어야 한다.

    중심점이 틀리면 기상 격자·쉼터 거리·위험도가 전부 조용히 오염된다 —
    예외도 안 나고 지도에 점 하나가 엉뚱한 데 찍힐 뿐이라 눈으로만 발견된다.
    실제로 원본 데이터의 포항시 상대1·2동이 147km 떨어져 있었다."""
    suspects = B.check_region_coords(B.load_regions())
    assert not suspects, (
        "시군구에서 멀리 떨어진 읍면동: "
        + ", ".join(f"{r['sigungu']} {r['eupmyeondong']} ({d:.0f}km)" for d, r in suspects)
    )


def test_illness_age_groups_preserved():
    """연령대가 집계에서 유실되면 안 된다(80세 이상 비중 근거가 사라진다)."""
    regions = B.load_regions()
    illness = B.load_heat_illness(regions)
    groups = {row["age_group"] for row in illness}
    assert "80대 이상" in groups, f"연령대 버킷이 유실됨: {sorted(groups)}"

    # PK가 (region_code, year, age_group)이므로 이 조합은 유일해야 한다.
    keys = [(r["region_code"], r["year"], r["age_group"]) for r in illness]
    assert len(keys) == len(set(keys)), "중복 키 - INSERT 시 IntegrityError가 난다"


def test_older_skew_scores_higher_at_same_elderly_ratio():
    """같은 65+ 비율이라면 85+ 쏠림이 큰 지역의 점수가 더 높아야 한다(설계 의도 자체)."""
    scores, vmap = _all_scores()
    ranked = sorted(
        ((vmap[c]["elderly_85_ratio"] / vmap[c]["elderly_ratio"], scores[c]["elderly_score"], vmap[c]["elderly_ratio"])
         for c in scores if vmap.get(c, {}).get("elderly_ratio")),
        key=lambda t: t[0],
    )
    lowest_skew, highest_skew = ranked[0], ranked[-1]
    # 같은 65+ 비율로 정규화해 비교 (기준선 영향 제거)
    assert highest_skew[1] / highest_skew[2] > lowest_skew[1] / lowest_skew[2]


if __name__ == "__main__":
    test_heat_illness_maps_all_sigungu()
    print("OK: heat_illness_gyeongbuk.csv 시군구명 전부 매핑됨")
    test_eupmyeondong_inherits_sigungu_history()
    print("OK: 읍면동 history_score가 소속 시군구 값을 상속함")
    test_elderly_score_applies_skew_within_bounds()
    print(f"OK: 초고령 쏠림 보정이 ±{B.ELDERLY_SKEW_MAX_ADJ:.0%} 안에서 적용됨")
    test_elderly_score_scale_preserved()
    print("OK: 기준선 스케일 보존 - '고령인구 비율 높음' 근거가 실제로 발동함")
    test_older_skew_scores_higher_at_same_elderly_ratio()
    print("OK: 같은 고령화율이면 초고령 쏠림이 큰 지역이 더 높은 점수")
    test_scoring_uses_recent_years_only()
    print(f"OK: 위험도 점수는 최근 {B.SCORING_YEARS}년만 반영 (화면 표기는 전체 누적)")
    test_illness_age_groups_preserved()
    print("OK: 온열질환 연령대 보존 + 키 중복 없음")
    test_region_coords_within_parent_sigungu()
    print(f"OK: 모든 읍면동 중심점이 소속 시군구 {B.MAX_EMD_DISTANCE_KM}km 이내")
