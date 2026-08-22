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
