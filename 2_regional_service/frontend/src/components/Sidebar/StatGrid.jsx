import { riskColor } from '../../utils/risk';
import styles from './StatGrid.module.css';

export default function StatGrid({ summary }) {
  if (!summary) return <div className={styles.grid}>{[1,2,3,4].map(i => <div key={i} className={styles.skeleton} />)}</div>;

  const cards = [
    { val: summary.total_regions, label: '전체 지역', color: 'var(--accent)' },
    { val: summary.high_risk_count, label: '고위험 지역', color: 'var(--risk-crit)', alert: !!summary.high_risk_count },
    { val: summary.shelter_blind_spots, label: '쉼터 사각지대', color: 'var(--blind)', alert: !!summary.shelter_blind_spots },
    { val: (summary.shelters_total ?? 5605).toLocaleString(), label: '총 무더위쉼터', color: 'var(--accent)' },
  ];

  return (
    <div>
      <div className={styles.sectionTitle}>📊 현황 요약</div>
      <div className={styles.grid}>
        {cards.map((c, i) => (
          <div key={i} className={`${styles.card} ${c.alert ? styles.alert : ''} fade-in`}>
            <div className={styles.val} style={{ color: c.color }}>{c.val}</div>
            <div className={styles.lbl}>{c.label}</div>
          </div>
        ))}
        <div className={`${styles.card} ${styles.wide} fade-in`}>
          <div className={styles.val} style={{ color: riskColor(summary.avg_static_risk) }}>
            {summary.avg_static_risk}
          </div>
          <div className={styles.lbl}>평균 정적 위험도</div>
        </div>
      </div>
    </div>
  );
}
