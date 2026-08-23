import { useState, useEffect } from 'react';
import styles from './SendPreviewModal.module.css';

const TABS = [
  { key: 'sms', label: '인부 문자' },
  { key: 'tts', label: '전화(TTS)' },
  { key: 'shelter', label: '쉼터 안내' },
];

// 더미 수신자 목록 (실제 운용 시 지역 담당자 API 연동)
const DUMMY_RECIPIENTS = [
  { id: 1, name: '서룡1리 · 생활지원사 김미경', phone: '010-****-1234', checked: true },
  { id: 2, name: '덕미리 · 지킴이 이찬원', phone: '010-****-5678', checked: true },
];

function buildSmsText(region) {
  const date = new Date().toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'short' });
  return `[경상북도 폭염 순찰]
${date} · ${region.region_name}
오늘 위험 단계: ${region.risk_grade}

- 낮 최고 체감 ${region.feels_like_c}°C
- 독거노인 추정 ${Math.round((region.elderly_65_plus ?? 0) * 0.12)}가구
- 걸어갈 쉼터 ${region.within_400m_count ?? 0}개

오늘 14시 전까지 고령·독거 가구의 안부를 확인해 주세요. 응답이 없는 가구는 아래 번호로 알려 주세요.`;
}

function buildTtsText(region) {
  return `경상북도 폭염 순찰 안내입니다.
${region.region_name}은 오늘 위험 단계가 ${region.risk_grade}입니다.
낮 최고 체감온도는 ${region.feels_like_c}도이고 걸어갈 쉼터가 ${region.within_400m_count ?? 0}개 있습니다.
오늘 오후 2시 전까지 고령·독거 가구의 안부를 확인해 주세요.
응답이 없는 가구는 안내되는 번호로 알려 주세요.`;
}

function buildShelterText(region, shelters) {
  const top3 = (shelters ?? []).slice(0, 3);
  const shelterLines = top3.length > 0
    ? top3.map((s, i) => `${i + 1}. ${s.shelter_name} · ${s.road_address || s.lot_address || ''}`)
        .join('\n')
    : '가까운 쉼터 정보를 확인 중입니다.';

  return `[경상북도 폭염 쉼터 안내]
${new Date().toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'short' })} · ${region.region_name}

가까운 무더위쉼터를 안내해 드립니다.
${shelterLines}

가까운 쉼터에서 더위를 피하세요. 도착하시면 이 문자에 '도착'이라고 답장해 주세요.`;
}

export default function SendPreviewModal({ region, type, areaShelters, onClose }) {
  const [tab, setTab] = useState(type === 'shelter' ? 'shelter' : type === 'tts' ? 'tts' : 'sms');
  const [recipients, setRecipients] = useState(DUMMY_RECIPIENTS);

  // sync tab when type prop changes
  useEffect(() => {
    if (type === 'shelter') setTab('shelter');
    else if (type === 'tts') setTab('tts');
    else setTab('sms');
  }, [type]);

  const checkedCount = recipients.filter(r => r.checked).length;

  function toggleRecipient(id) {
    setRecipients(prev => prev.map(r => r.id === id ? { ...r, checked: !r.checked } : r));
  }

  function getPreviewText() {
    if (tab === 'sms') return buildSmsText(region);
    if (tab === 'tts') return buildTtsText(region);
    return buildShelterText(region, areaShelters);
  }

  function getPreviewTitle() {
    if (tab === 'sms') return '문자 미리보기';
    if (tab === 'tts') return '전화(TTS) 대본 미리보기';
    return '쉼터 안내 문자 미리보기';
  }

  function getSendBtnLabel() {
    if (tab === 'sms') return '문자 발송';
    if (tab === 'tts') return '전화 발신';
    return '문자 발송';
  }

  return (
    <div className={styles.overlay} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal}>
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.title}>발송 미리보기</div>
          <button className={styles.closeBtn} onClick={onClose}>✕</button>
        </div>

        {/* Tabs */}
        <div className={styles.tabs}>
          {TABS.map(t => (
            <button
              key={t.key}
              className={`${styles.tab} ${tab === t.key ? styles.tabActive : ''}`}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className={styles.body}>
          {/* Recipients */}
          <div className={styles.column}>
            <div className={styles.colTitle}>받는 사람 <span className={styles.colCount}>({checkedCount})</span></div>
            <div className={styles.recipientList}>
              {recipients.map(r => (
                <label key={r.id} className={styles.recipient}>
                  <input
                    type="checkbox"
                    checked={r.checked}
                    onChange={() => toggleRecipient(r.id)}
                    className={styles.checkbox}
                  />
                  <div>
                    <div className={styles.recipientName}>{r.name}</div>
                    <div className={styles.recipientPhone}>{r.phone}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Preview */}
          <div className={styles.column}>
            <div className={styles.colTitle}>{getPreviewTitle()}</div>
            {tab === 'tts' && (
              <div className={styles.ttsHint}>AI가 분께 이 대본대로 전화를 걸어 안부를 확인합니다.</div>
            )}
            {tab === 'shelter' && (
              <div className={styles.shelterOptions}>
                <label className={styles.optionLabel}>
                  <input type="checkbox" defaultChecked={false} className={styles.checkbox} />
                  도착 시 위치 공유 요청 포함 (지킴이 동의 시 GPS로 자동 확인)
                </label>
                <label className={styles.optionLabel}>
                  <input type="checkbox" defaultChecked={false} className={styles.checkbox} />
                  쉼터 담당자에게 방문 예정 알림 연계
                </label>
                <div className={styles.gpsWarning}>
                  ⚠️ GPS 도착 확인이 사전 담당자와 당사자에게 안전상 별도 동의를 받아야 합니다. 이 프로토타입은 해당 단계 없이 실제로 전송하거나 전송하지 않습니다.
                </div>
              </div>
            )}
            <div className={styles.previewBox}>
              <pre className={styles.previewText}>{getPreviewText()}</pre>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className={styles.footer}>
          <button className={styles.sendBtn} onClick={onClose}>
            {getSendBtnLabel()}
          </button>
        </div>
      </div>
    </div>
  );
}
