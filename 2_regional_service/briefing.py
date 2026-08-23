"""AI 브리핑 — 파이프라인이 계산한 사실을 현장 담당자용 서술로 바꾼다.

설계 원칙: **숫자는 코드가 계산하고, 모델은 문장만 만든다.**
모델에는 이미 확정된 사실(지역명·점수·건수)만 넘기고 DB 접근 권한을 주지 않는다.
모델이 숫자를 지어내는 순간 "판단 근거를 검증할 수 있어야 한다"는 이 프로젝트의
전제가 무너지기 때문이다. 그래서 fact 수집(collect_facts)과 서술(generate)을 분리했다.

ANTHROPIC_API_KEY가 없거나 API 호출이 실패하면 규칙 기반 문장으로 degrade한다.
브리핑은 부가 기능이므로, 이것 때문에 대시보드가 멈추면 안 된다.
"""

import hashlib
import json
import os

from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-haiku-4-5-20251001"
TOP_N = 3  # 브리핑에 이름을 올릴 최우선 지역 수

_cache = {}


# ---------------------------------------------------------------- facts

def collect_facts(regions, summary):
    """브리핑에 쓸 사실만 추린다. 여기서 나온 숫자가 최종값이며 모델은 이걸 바꿀 수 없다."""
    # 현장 인력이 실제로 찾아가는 단위는 읍·면·동이다. 시군구 행은 집계값이라
    # 함께 순위에 넣으면 같은 지역이 두 번 나온다.
    villages = [r for r in regions if r.get("level") == "eupmyeondong"]

    tiers = {}
    for r in villages:
        lv = r.get("temp_level")
        if lv:
            tiers[lv] = tiers.get(lv, 0) + 1

    # 위험 단계이면서 도보권 쉼터도 없는 곳 — 더위를 피할 곳 자체가 없는 지역이다.
    # 대시보드에서는 두 필터를 동시에 걸 수 없어 이 교집합이 잘 드러나지 않는다.
    no_refuge = [r for r in villages
                 if r.get("is_blind_spot") and (r.get("final_risk") or 0) >= 55]

    top = sorted(villages, key=lambda r: -(r.get("final_risk") or 0))[:TOP_N]
    priority = [{
        "지역": r["region_name"],
        "위험도": r.get("final_risk"),
        "등급": r.get("risk_grade"),
        "체감온도": r.get("feels_like_c"),
        "판단근거": r.get("reasons", []),
    } for r in top]

    return {
        "기준시각": (villages[0].get("announce_time") if villages else None),
        "대상_읍면동_수": len(villages),
        "폭염단계_분포": tiers,
        "쉼터사각지대_수": summary.get("shelter_blind_spots"),
        "고위험이면서_쉼터없는_읍면동_수": len(no_refuge),
        "최우선_지역": priority,
    }


# ---------------------------------------------------------------- render

def _fallback_text(facts):
    """API 없이 만드는 규칙 기반 브리핑. 문장은 투박해도 숫자는 정확하다."""
    tiers = facts["폭염단계_분포"]
    worst = max(tiers, key=tiers.get) if tiers else "관심"
    lines = [
        f"경북 읍·면·동 {facts['대상_읍면동_수']}곳 중 {tiers.get(worst, 0)}곳이 '{worst}' 단계입니다."
    ]
    if facts["고위험이면서_쉼터없는_읍면동_수"]:
        lines.append(
            f"이 가운데 도보권에 무더위쉼터가 없는 고위험 지역이 "
            f"{facts['고위험이면서_쉼터없는_읍면동_수']}곳으로, 가장 먼저 확인이 필요합니다."
        )
    if facts["최우선_지역"]:
        names = ", ".join(f"{p['지역']}(위험도 {p['위험도']})" for p in facts["최우선_지역"])
        lines.append(f"우선 순회 대상은 {names} 순입니다.")
    return " ".join(lines)


_SYSTEM = """당신은 경상북도 폭염대응TF의 상황 브리핑 담당자다.
현장 인력이 오늘 어느 마을부터 확인해야 하는지 판단할 수 있게 3~4문장으로 브리핑한다.

반드시 지킬 것:
- 주어진 사실에 있는 숫자와 지역명만 쓴다. 없는 값을 추정하거나 만들어내지 않는다.
- 각 지역의 근거는 그 지역 항목에 적힌 것만 쓴다. 한 지역에만 있는 특성을 다른
  지역까지 묶어 말하지 않는다. "세 지역 모두 ~하다"는 세 지역 근거에 모두
  나와 있을 때만 쓸 수 있다.
- 정보를 나열하지 말고 "어디부터 가라"는 판단을 내린다. 그 근거를 함께 말한다.
- 공문 말투로 간결하게 쓴다. 인사말, 머리말, 목록 기호, 마크다운을 쓰지 않는다.
- 사실에 없는 대응 지침(예: 특정 시간대 방문, 특정 물품 배포)을 지어내지 않는다."""


def _call_claude(facts):
    """Claude API 호출. 실패는 호출부에서 폴백으로 처리하도록 그대로 올린다."""
    from anthropic import Anthropic

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model=MODEL,
        max_tokens=500,
        system=_SYSTEM,
        messages=[{
            "role": "user",
            "content": "오늘의 상황 사실:\n"
                       + json.dumps(facts, ensure_ascii=False, indent=2)
                       + "\n\n위 사실만으로 브리핑을 작성하라.",
        }],
    )
    return "".join(block.text for block in msg.content if block.type == "text").strip()


def generate(regions, summary):
    """브리핑 텍스트를 반환. 같은 데이터면 캐시를 재사용한다.

    파이프라인 산출물이 바뀌지 않으면 브리핑도 동일하므로, 사실 다이제스트를 키로
    캐싱해 페이지를 열 때마다 API를 호출하는 낭비를 막는다.
    """
    facts = collect_facts(regions, summary)
    # 프롬프트·모델도 키에 넣는다. 사실만으로 키를 만들면 프롬프트를 고쳐도 캐시된
    # 옛 문장이 그대로 나와, 수정이 반영되지 않은 걸 모른 채 넘어가게 된다.
    key = hashlib.sha256(
        json.dumps([facts, _SYSTEM, MODEL], ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    if key in _cache:
        return _cache[key]

    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            result = {"text": _call_claude(facts), "source": "ai", "model": MODEL}
        except Exception as e:
            # 키가 틀렸거나 네트워크가 끊긴 경우. 브리핑 없이도 대시보드는 돌아야 한다.
            result = {"text": _fallback_text(facts), "source": "fallback",
                      "error": f"{type(e).__name__}: {e}"}
    else:
        result = {"text": _fallback_text(facts), "source": "fallback",
                  "error": "ANTHROPIC_API_KEY 미설정"}

    result["facts"] = facts
    _cache[key] = result
    return result
