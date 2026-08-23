import styles from './MapLegend.module.css';

export default function MapLegend() {
  return (
    <div className={styles.legend}>
      <div className={styles.title}>위험도 범례</div>
      <div className={styles.item}><div className={styles.dot} style={{ background: '#ef4444' }} /><span>매우 높음 (≥75)</span></div>
      <div className={styles.item}><div className={styles.dot} style={{ background: '#f97316' }} /><span>높음 (55–74)</span></div>
      <div className={styles.item}><div className={styles.dot} style={{ background: '#f59e0b' }} /><span>보통 (35–54)</span></div>
      <div className={styles.item}><div className={styles.dot} style={{ background: '#10b981' }} /><span>낮음 (&lt;35)</span></div>
      <div className={styles.divider} />
      <div className={styles.item}><div className={`${styles.dot} ${styles.blind}`} /><span>쉼터 사각지대</span></div>
      <div className={styles.divider} />
      <div className={styles.item}>
        <div className={styles.dot} style={{ background: '#10b981', boxShadow: '0 0 8px rgba(16,185,129,.6)' }} />
        <span>무더위쉼터</span>
      </div>
    </div>
  );
}
