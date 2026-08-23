import styles from './Header.module.css';

const LEVELS = [
  { key: 'sigungu', label: '시군구' },
  { key: 'eupmyeondong', label: '읍면동' },
  { key: 'all', label: '전체' },
];

export default function Header({ level, onLevelChange, showShelters, onShelterToggle, onSearch, asOf }) {
  return (
    <header className={styles.header}>
      <div className={styles.left}>
        <span className={styles.fire}>🔥</span>
        <div>
          <div className={styles.logo}>HOSU</div>
          <div className={styles.sub}>경북 폭염 위험도 대시보드</div>
        </div>
      </div>

      <div className={styles.right}>
        <button
          className={`${styles.shelterBtn} ${showShelters ? styles.shelterBtnActive : ''}`}
          onClick={onShelterToggle}
        >
          🏠 쉼터 보기
        </button>

        <div className={styles.levelToggle}>
          {LEVELS.map(({ key, label }) => (
            <button
              key={key}
              className={`${styles.levelBtn} ${level === key ? styles.levelBtnActive : ''}`}
              onClick={() => onLevelChange(key)}
            >
              {label}
            </button>
          ))}
        </div>

        <div className={styles.searchBox}>
          <span className={styles.searchIcon}>🔍</span>
          <input
            type="text"
            className={styles.searchInput}
            placeholder="지역/쉼터 검색…"
            onChange={e => onSearch(e.target.value)}
          />
        </div>

        <div className={styles.ts}>
          <span className={styles.liveDot} />
          <span>{asOf ? asOf.replace('T', ' ').slice(0, 16) : '로딩 중…'}</span>
        </div>
      </div>
    </header>
  );
}
