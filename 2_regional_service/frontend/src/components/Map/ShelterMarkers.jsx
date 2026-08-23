import { CircleMarker, Tooltip, Popup } from 'react-leaflet';

export default function ShelterMarkers({ shelters }) {
  if (!shelters || shelters.length === 0) return null;

  return shelters.map((s, idx) => (
    <CircleMarker
      key={s.id ?? `shelter-${idx}-${s.lat}-${s.lon}`}
      center={[s.lat, s.lon]}
      radius={6}
      pathOptions={{
        fillColor: '#059669',
        fillOpacity: 0.9,
        color: '#ffffff',
        weight: 2,
      }}
    >
      <Tooltip direction="top" offset={[0, -6]}>
        🏠 {s.shelter_name} ({s.sigungu})
      </Tooltip>
      <Popup maxWidth={300}>
        <div style={{ padding: 4 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 6 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: '#0f172a' }}>🏠 {s.shelter_name}</div>
            <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 4, background: '#d1fae5', color: '#065f46', fontWeight: 700 }}>
              {s.shelter_type || '쉼터'}
            </span>
          </div>
          <div style={{ fontSize: 11.5, color: '#475569', marginBottom: 8 }}>
            📍 {s.road_address || s.lot_address || '-'}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, background: '#f8fafc', border: '1px solid #e2e8f0', padding: 8, borderRadius: 8, fontSize: 11, marginBottom: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', color: '#64748b' }}>
              <span>수용인원</span><span style={{ fontWeight: 700, color: '#0f172a' }}>{s.capacity ? s.capacity + '명' : '-'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', color: '#64748b' }}>
              <span>냉방기기</span><span style={{ fontWeight: 700, color: '#0f172a' }}>{s.aircons ?? 0}대 / {s.fans ?? 0}대</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', color: '#64748b' }}>
              <span>야간운영</span><span style={{ fontWeight: 700, color: '#0f172a' }}>{s.night_open || '-'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', color: '#64748b' }}>
              <span>휴일운영</span><span style={{ fontWeight: 700, color: '#0f172a' }}>{s.weekend_open || '-'}</span>
            </div>
          </div>
          <a
            href={`https://map.kakao.com/link/map/${encodeURIComponent(s.shelter_name)},${s.lat},${s.lon}`}
            target="_blank"
            rel="noreferrer"
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5,
              width: '100%', padding: '7px 10px', background: '#2563eb', color: '#fff',
              fontSize: 11.5, fontWeight: 700, borderRadius: 6, textDecoration: 'none',
              boxShadow: '0 1px 3px rgba(37,99,235,0.3)',
            }}
          >
            🗺️ 카카오맵에서 길찾기
          </a>
        </div>
      </Popup>
    </CircleMarker>
  ));
}
