import { useState, useEffect } from 'react';
import { riskColor, riskClass } from '../../utils/risk';
import { fetchShelters } from '../../api/hosuApi';
import SendPreviewModal from '../Modal/SendPreviewModal';
import styles from './DetailPanel.module.css';

function BreakdownBar({ label, score }) {
  const s = score ?? 0;
  const c = riskColor(s);
  return (
    <div className={styles.bdItem}>
      <div className={styles.bdHdr}>
        <span className={styles.bdLbl}>{label}</span>
        <span className={styles.bdVal} style={{ color: c }}>{s.toFixed(1)}</span>
      </div>
      <div className={styles.bdBar}>
        <div className={styles.bdFill} style={{ width: `${s}%`, background: c }} />
      </div>
    </div>
  );
}

export default function DetailPanel({ region, onClose, onFlyTo }) {
  const [areaShelters, setAreaShelters] = useState([]);
  const [sheltersLoading, setSheltersLoading] = useState(false);
  const [sheltersLoaded, setSheltersLoaded] = useState(false);
  const [modalType, setModalType] = useState(null); // 'call' | 'visit' | 'shelter'

  useEffect(() => {
    // reset state when region changes
    setAreaShelters([]);
    setSheltersLoaded(false);
  }, [region?.region_code]);

  if (!region) return null;

  const r = region;
  const color = riskColor(r.final_risk);
  const cls = riskClass(r.final_risk);

  async function loadAreaShelters() {
    setSheltersLoading(true);
    try {
      const data = await fetchShelters({ sigungu: r.sigungu, limit: 100 });
      setAreaShelters(data.shelters);
      setSheltersLoaded(true);
      if (data.shelters.length > 0) {
        onFlyTo({ lat: r.lat, lon: r.lon, zoom: r.level === 'sigungu' ? 11 : 13 });
      }
    } catch (e) {
      console.error(e);
    } finally {
      setSheltersLoading(false);
    }
  }

  return (
    <>
      <div className={`${styles.panel} ${styles.open}`}>
        <button className={styles.close} onClick={onClose}>← 닫기</button>

        {/* 지역명 */}
        <div className={styles.name}>{r.region_name}</div>
        <div className={styles.code}>{r.region_code}</div>

        {/* 위험도 카드 */}
        <div className={styles.scoreCard} style={{ borderColor: color + '30' }}>
          <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 3, background: color }} />
          <div className={styles.scoreVal} style={{ color }}>{r.final_risk}</div>
          <span className={`${styles.badge} ${styles[cls]}`} style={{ fontSize: 12, padding: '4px 14px' }}>
            {r.risk_grade}
          </span>
        </div>

        {/* 기상 */}
        <div className={styles.sec}>
          <div className={styles.secTitle}>🌡️ 실시간 기상 (기상청 실측)</div>
          <div className={styles.row}><span className={styles.rowL}>체감온도</span><span className={styles.rowV} style={{ color }}>{r.feels_like_c}°C</span></div>
          <div className={styles.row}><span className={styles.rowL}>현재 기온</span><span className={styles.rowV}>{r.temperature_c ? r.temperature_c + '°C' : '-'}</span></div>
          <div className={styles.row}><span className={styles.rowL}>현재 습도</span><span className={styles.rowV}>{r.humidity_pct ? r.humidity_pct + '%' : '-'}</span></div>
          <div className={styles.row}>
            <span className={styles.rowL}>폭염 단계</span>
            <span className={styles.rowV}><span className={`${styles.badge} ${styles[cls]}`}>{r.temp_level}</span></span>
          </div>
          {r.announce_time && (
            <div className={styles.row}><span className={styles.rowL}>발표시각</span><span className={styles.rowV} style={{ fontSize: 10, color: 'var(--text-3)' }}>{r.announce_time}</span></div>
          )}
        </div>

        {/* 위험요소 분석 */}
        <div className={styles.sec}>
          <div className={styles.secTitle}>📊 위험요소 분석</div>
          <BreakdownBar label="고령인구" score={r.elderly_score} />
          <BreakdownBar label="쉼터접근성" score={r.shelter_score} />
          <BreakdownBar label="과거이력" score={r.history_score} />
        </div>

        {/* 쉼터 현황 */}
        <div className={styles.sec}>
          <div className={styles.secTitle}>🏠 쉼터 현황</div>
          <div className={styles.row}><span className={styles.rowL}>관내 쉼터</span><span className={styles.rowV}>{r.shelter_count ?? '-'}개</span></div>
          <div className={styles.row}><span className={styles.rowL}>도보 5분권</span><span className={styles.rowV}>{r.within_400m_count ?? '-'}개</span></div>
          <div className={styles.row}><span className={styles.rowL}>최근접 거리</span><span className={styles.rowV}>{r.nearest_distance_m ? r.nearest_distance_m.toFixed(0) + 'm' : '-'}</span></div>
          <div className={styles.row}>
            <span className={styles.rowL}>사각지대</span>
            <span className={`${styles.rowV} ${r.is_blind_spot ? styles.no : styles.yes}`}>
              {r.is_blind_spot ? '⚠ 사각지대' : '✅ 정상'}
            </span>
          </div>

          {!sheltersLoaded && (
            <button className={styles.shelterBtn} onClick={loadAreaShelters} disabled={sheltersLoading}>
              {sheltersLoading ? '로딩 중…' : '🔍 관내 쉼터 지도에 표시하기'}
            </button>
          )}

          {sheltersLoaded && areaShelters.length === 0 && (
            <div className={styles.noShelter}>관내 등록된 쉼터가 없습니다 (사각지대).</div>
          )}

          {areaShelters.length > 0 && (
            <div className={styles.shelterList}>
              {areaShelters.slice(0, 15).map(s => (
                <div
                  key={s.id}
                  className={styles.shelterItem}
                  onClick={() => onFlyTo({ lat: s.lat, lon: s.lon, zoom: 16 })}
                >
                  <div className={styles.sliName}>
                    <span>🏠 {s.shelter_name}</span>
                    {s.capacity && <span style={{ color: '#10b981' }}>{s.capacity}명</span>}
                  </div>
                  <div className={styles.sliAddr}>{s.road_address || s.lot_address}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 취약인구 */}
        <div className={styles.sec}>
          <div className={styles.secTitle}>👥 취약인구</div>
          <div className={styles.row}><span className={styles.rowL}>총 인구</span><span className={styles.rowV}>{(r.total_population ?? 0).toLocaleString()}명</span></div>
          <div className={styles.row}><span className={styles.rowL}>65세 이상</span><span className={styles.rowV}>{(r.elderly_65_plus ?? 0).toLocaleString()}명 ({((r.elderly_ratio ?? 0) * 100).toFixed(1)}%)</span></div>
          <div className={styles.row}><span className={styles.rowL}>75세 이상</span><span className={styles.rowV}>{((r.elderly_75_ratio ?? 0) * 100).toFixed(1)}%</span></div>
          <div className={styles.row}><span className={styles.rowL}>85세 이상 (초고령)</span><span className={styles.rowV}>{((r.elderly_85_ratio ?? 0) * 100).toFixed(1)}%</span></div>
        </div>

        {/* 위험한 이유 */}
        {r.reasons && r.reasons.length > 0 && r.reasons[0] !== '특이 위험 요소 없음' && (
          <div className={styles.sec}>
            <div className={styles.secTitle}>⚠️ 위험한 이유</div>
            {r.reasons.map((t, i) => (
              <div key={i} className={styles.reason}><span>•</span><span>{t}</span></div>
            ))}
            <div className={styles.reasonSrc}>
              기상청 초단기실황 · 질병관리청 온열질환 감시데이터 ·
              행정안전부 무더위쉼터 표준데이터 · 읍면동 연령별 주민등록 인구
            </div>
          </div>
        )}

        {/* 오늘의 액션 */}
        <div className={styles.sec}>
          <div className={styles.secTitle}>📋 오늘의 액션</div>
          <div className={styles.actionGrid}>
            <div className={styles.actionCard} onClick={() => setModalType('call')}>
              <div className={styles.actionIcon}>📞</div>
              <div className={styles.actionTitle}>전화 확인</div>
              <div className={styles.actionDesc}>오늘 14시 이전 고령·독거 가구 안부 전화</div>
              <button className={styles.actionBtn}>AI 전화 걸기</button>
            </div>
            <div className={styles.actionCard} onClick={() => setModalType('visit')}>
              <div className={styles.actionIcon}>🚶</div>
              <div className={styles.actionTitle}>방문 확인</div>
              <div className={styles.actionDesc}>전화 미응답 시 생활지원사, 이장에게 직접 방문 요청</div>
              <button className={styles.actionBtn}>순찰 요청하기</button>
            </div>
            <div className={styles.actionCard} onClick={() => setModalType('shelter')}>
              <div className={styles.actionIcon}>🏠</div>
              <div className={styles.actionTitle}>쉼터 안내</div>
              <div className={styles.actionDesc}>가장 가까운 무더위 쉼터로 안내 문자 발송</div>
              <button className={styles.actionBtn}>쉼터 안내 문자 발송</button>
            </div>
          </div>
        </div>
      </div>

      {modalType && (
        <SendPreviewModal
          region={r}
          type={modalType}
          areaShelters={areaShelters}
          onClose={() => setModalType(null)}
        />
      )}
    </>
  );
}
