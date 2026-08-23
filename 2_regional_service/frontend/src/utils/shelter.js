// 쉼터 지표 표시 규칙. 세 가지가 여기 모여 있다.
//
// 1) 판정 기준값은 /api/summary 로 파이프라인 상수(build.BLIND_SPOT_METERS 등)를 받아 쓴다.
//    화면이 값을 따로 들고 있으면 기준이 바뀔 때 라벨만 옛 숫자로 남는다.
// 2) nearest_distance_m 은 level 에 따라 의미가 다르다. 읍면동은 자기 중심점에서 잰
//    실측이지만, 시군구는 중심점 하나로 수십 km를 대표할 수 없어 관할 읍면동의 평균이다.
//    시군구 행을 '최근접 거리'라고 부르면 틀린 값을 정확한 값처럼 보여주게 된다.
// 3) is_blind_spot 의 null 은 '정상'이 아니라 '판정 단위가 아님'이다. 시군구가 그렇다.
//    null 을 falsy 로 뭉개면 판정하지 않은 것을 안전하다고 단정하게 된다.

const FALLBACK = { walk_speed_m_per_min: 80, blind_spot_walk_min: 15 };

export const criteria = summary => ({ ...FALLBACK, ...(summary || {}) });

export const walkMin = (m, summary) =>
  Math.round(m / criteria(summary).walk_speed_m_per_min);

export const isSigungu = r => r.level === 'sigungu';

export const distanceLabel = r =>
  isSigungu(r) ? '읍면동 평균 거리' : '최근접 거리';

export const distanceHint = r =>
  isSigungu(r)
    ? '시군구는 중심점 하나로 잴 수 없어 관할 읍면동의 최근접 거리를 평균한 값입니다'
    : '마을 중심점에서 가장 가까운 쉼터까지의 직선거리';

/** 사각지대 판정 표시. null 은 판정 대상이 아니라는 뜻이므로 '정상'과 구분한다. */
export function blindSpotDisplay(r, summary) {
  if (r.is_blind_spot == null) {
    return {
      text: '읍면동 단위로 판정',
      tone: 'na',
      hint: '시군구는 수십 km에 걸쳐 있어 중심점 하나로 접근성을 판정할 수 없습니다',
    };
  }
  const hint = `마을 중심에서 최근접 쉼터까지 도보 ${criteria(summary).blind_spot_walk_min}분 초과 시 사각지대`;
  return r.is_blind_spot
    ? { text: '⚠ 도보권 밖 (사각지대)', tone: 'no', hint }
    : { text: '✅ 도보권 내', tone: 'yes', hint };
}
