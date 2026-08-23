import BriefingCard from './BriefingCard';
import StatGrid from './StatGrid';
import PriorityList from './PriorityList';
import styles from './Sidebar.module.css';

export default function Sidebar({ summary, regions, selectedCode, onSelectRegion }) {
  return (
    <aside className={styles.sidebar}>
      <BriefingCard />
      <StatGrid summary={summary} />
      <PriorityList regions={regions} selectedCode={selectedCode} onSelect={onSelectRegion} />
    </aside>
  );
}
