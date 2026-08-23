import { riskColor, riskClass } from '../../utils/risk';
import styles from './PriorityList.module.css';

export default function PriorityList({ regions, selectedCode, onSelect }) {
  const sorted = [...regions].sort((a, b) => b.final_risk - a.final_risk).slice(0, 15);

  return (
    <div>
      <div className={styles.sectionTitle}>🏆 우선 대응 지역</div>
      <div className={styles.list}>
        {sorted.map((r, i) => (
          <div
            key={r.region_code}
            className={`${styles.item} ${selectedCode === r.region_code ? styles.active : ''} fade-in`}
            style={{ animationDelay: `${i * 0.03}s` }}
            onClick={() => onSelect(r.region_code)}
          >
            <div className={`${styles.rank} ${i < 3 ? styles.top : ''}`}>{i + 1}</div>
            <div className={styles.info}>
              <div className={styles.name}>{r.region_name}</div>
              <div className={styles.sub}>
                <span className={`${styles.badge} ${styles[riskClass(r.final_risk)]}`}>
                  {r.risk_grade}
                </span>
                {r.is_blind_spot && <span className={styles.tagBlind}>쉼터사각</span>}
              </div>
            </div>
            <div className={styles.score} style={{ color: riskColor(r.final_risk) }}>
              {r.final_risk}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
