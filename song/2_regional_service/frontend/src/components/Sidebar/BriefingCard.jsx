import { useBriefing } from '../../hooks/useBriefing';
import styles from './BriefingCard.module.css';

export default function BriefingCard() {
  const { briefing, loading } = useBriefing();

  return (
    <div>
      <div className={styles.title}>
        🤖 오늘의 브리핑
        {briefing && (
          <span className={`${styles.badge} ${briefing.source === 'ai' ? styles.ai : styles.fallback}`}>
            {briefing.source === 'ai' ? 'AI 생성' : '규칙 기반'}
          </span>
        )}
      </div>
      <div className={styles.card}>
        {loading && <span className={styles.loading}>브리핑 생성 중…</span>}
        {briefing && <p className="fade-in">{briefing.text}</p>}
      </div>
    </div>
  );
}
