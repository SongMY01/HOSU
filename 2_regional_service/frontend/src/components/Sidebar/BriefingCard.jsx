import { useBriefing } from '../../hooks/useBriefing';
import styles from './BriefingCard.module.css';

export default function BriefingCard() {
  const { briefing, loading } = useBriefing();

  return (
    <div>
      <div className={styles.title}>
        🤖 오늘의 브리핑
        {briefing && briefing.source === 'ai' && (
          <span className={`${styles.badge} ${styles.ai}`}>AI 생성</span>
        )}
      </div>
      <div className={styles.card}>
        {loading && <span className={styles.loading}>브리핑 생성 중…</span>}
        {briefing && <p className="fade-in">{briefing.text}</p>}
      </div>
    </div>
  );
}
