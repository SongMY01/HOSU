import { CircleMarker, Tooltip } from 'react-leaflet';
import { riskColor } from '../../utils/risk';
import { walkMin, isSigungu } from '../../utils/shelter';

export default function RegionMarkers({ regions, onSelect, summary }) {
  return regions.map(r => {
    const color = riskColor(r.final_risk);
    const rad = isSigungu(r) ? 14 : 8;
    const isBlind = r.is_blind_spot === 1;
    const dist = r.nearest_distance_m;

    return (
      <CircleMarker
        key={r.region_code}
        center={[r.lat, r.lon]}
        radius={rad}
        pathOptions={{
          fillColor: color,
          fillOpacity: 0.6,
          color: isBlind ? '#a855f7' : 'rgba(255,255,255,.25)',
          weight: isBlind ? 3 : 2,
          dashArray: isBlind ? '5 5' : undefined,
        }}
        eventHandlers={{ click: () => onSelect(r) }}
      >
        <Tooltip direction="top" offset={[0, -8]}>
          <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 3 }}>{r.region_name}</div>
          <div style={{ fontWeight: 600, color }}>위험도 {r.final_risk} · {r.risk_grade}</div>
          <div style={{ fontSize: 10, color: '#9ca3af', marginTop: 2 }}>
            체감온도 {r.feels_like_c}°C ({r.temp_level})
          </div>
          {/* 거리가 없으면 눈으로는 옆 마을과 구분되지 않아 판정이 자의적으로 보인다.
              시군구의 거리는 자기 중심점이 아니라 관할 읍면동 평균이므로 그렇게 부른다. */}
          {dist != null && (
            <div style={{ fontSize: 10, color: isBlind ? '#c4b5fd' : '#9ca3af', marginTop: 2 }}>
              {isSigungu(r) ? '읍면동 평균 쉼터 거리' : '가장 가까운 쉼터'}{' '}
              {Math.round(dist).toLocaleString()}m · 도보 {walkMin(dist, summary)}분
              {r.shelter_count ? ` · 관내 ${r.shelter_count}개` : ''}
            </div>
          )}
          {isBlind && (
            <div style={{ marginTop: 4 }}>
              <span style={{ background: 'rgba(168,85,247,.12)', color: '#a855f7', padding: '2px 6px', borderRadius: 4, fontSize: 9, fontWeight: 600 }}>
                🏠 쉼터 사각
              </span>
            </div>
          )}
        </Tooltip>
      </CircleMarker>
    );
  });
}
