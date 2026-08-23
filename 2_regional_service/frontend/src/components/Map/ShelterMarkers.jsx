import { CircleMarker, Tooltip, Popup } from 'react-leaflet';

export default function ShelterMarkers({ shelters }) {
  return shelters.map(s => (
    <CircleMarker
      key={s.id}
      center={[s.lat, s.lon]}
      radius={5}
      pathOptions={{
        fillColor: '#10b981',
        fillOpacity: 0.85,
        color: '#ffffff',
        weight: 1.5,
      }}
    >
      <Tooltip direction="top" offset={[0, -5]}>
        🏠 {s.shelter_name} ({s.sigungu})
      </Tooltip>
      <Popup maxWidth={300}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 6 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: '#fff' }}>🏠 {s.shelter_name}</div>
            <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, background: 'rgba(16,185,129,.15)', color: '#34d399', fontWeight: 600 }}>
              {s.shelter_type || '쉼터'}
            </span>
          </div>
          <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 8 }}>
            📍 {s.road_address || s.lot_address || '-'}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, background: 'rgba(255,255,255,.03)', padding: 8, borderRadius: 6, fontSize: 11, marginBottom: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', color: '#9ca3af' }}>
              <span>수용인원</span><span style={{ fontWeight: 600, color: '#f3f4f6' }}>{s.capacity ? s.capacity + '명' : '-'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', color: '#9ca3af' }}>
              <span>냉방기기</span><span style={{ fontWeight: 600, color: '#f3f4f6' }}>에어컨 {s.aircons}대 / 팬 {s.fans}대</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', color: '#9ca3af' }}>
              <span>야간운영</span><span style={{ fontWeight: 600, color: '#f3f4f6' }}>{s.night_open || '-'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', color: '#9ca3af' }}>
              <span>휴일운영</span><span style={{ fontWeight: 600, color: '#f3f4f6' }}>{s.weekend_open || '-'}</span>
            </div>
          </div>
          <a
            href={`https://map.kakao.com/link/map/${encodeURIComponent(s.shelter_name)},${s.lat},${s.lon}`}
            target="_blank"
            rel="noreferrer"
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5,
              width: '100%', padding: '6px 10px', background: '#3b82f6', color: '#fff',
              fontSize: 11, fontWeight: 600, borderRadius: 6, textDecoration: 'none',
            }}
          >
            🗺️ 카카오맵에서 길찾기
          </a>
        </div>
      </Popup>
    </CircleMarker>
  ));
}
