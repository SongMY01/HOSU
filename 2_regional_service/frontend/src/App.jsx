import { useState, useMemo, useCallback } from 'react';
import Header from './components/Header/Header';
import Sidebar from './components/Sidebar/Sidebar';
import MapView from './components/Map/MapView';
import DetailPanel from './components/Detail/DetailPanel';
import { useRegions } from './hooks/useRegions';
import { useSummary } from './hooks/useSummary';
import { fetchShelters } from './api/hosuApi';
import styles from './App.module.css';

export default function App() {
  const [level, setLevel] = useState('sigungu');
  const [searchQuery, setSearchQuery] = useState('');
  const [showShelters, setShowShelters] = useState(false);
  const [shelters, setShelters] = useState([]);
  const [selectedRegion, setSelectedRegion] = useState(null);
  const [flyTarget, setFlyTarget] = useState(null);

  const { regions, asOf, loading } = useRegions(level);
  const summary = useSummary();

  // Filter regions by search query
  const filteredRegions = useMemo(() => {
    if (!searchQuery.trim()) return regions;
    const q = searchQuery.trim().toLowerCase();
    return regions.filter(r =>
      r.region_name.toLowerCase().includes(q) || r.region_code.includes(q)
    );
  }, [regions, searchQuery]);

  // Toggle shelter layer
  const handleShelterToggle = useCallback(async () => {
    const next = !showShelters;
    setShowShelters(next);
    if (next && shelters.length === 0) {
      try {
        const data = await fetchShelters({ limit: 2000 });
        setShelters(data.shelters);
      } catch (e) {
        console.error('쉼터 로드 실패:', e);
      }
    }
  }, [showShelters, shelters]);

  // Select region from map click or sidebar
  const handleSelectRegion = useCallback((regionOrCode) => {
    const r = typeof regionOrCode === 'string'
      ? regions.find(x => x.region_code === regionOrCode)
      : regionOrCode;
    if (!r) return;
    setSelectedRegion(r);
    setFlyTarget({ lat: r.lat, lon: r.lon, zoom: r.level === 'sigungu' ? 11 : 13 });
  }, [regions]);

  const handleShowAreaShelters = useCallback((newShelters, target) => {
    setShelters(newShelters);
    setShowShelters(true);
    if (target) {
      setFlyTarget(target);
    }
  }, []);

  const handleCloseDetail = useCallback(() => {
    setSelectedRegion(null);
  }, []);

  const handleFlyTo = useCallback((target) => {
    setFlyTarget(target);
  }, []);

  return (
    <div className={styles.app}>
      {/* Loading overlay */}
      {loading && (
        <div className={styles.loading}>
          <div className={styles.spinner} />
          <div className={styles.loadingText}>데이터 로딩 중…</div>
        </div>
      )}

      <Header
        level={level}
        onLevelChange={(l) => { setLevel(l); setSelectedRegion(null); }}
        showShelters={showShelters}
        onShelterToggle={handleShelterToggle}
        onSearch={setSearchQuery}
        asOf={asOf}
      />

      <main className={styles.main}>
        <Sidebar
          summary={summary}
          regions={filteredRegions}
          selectedCode={selectedRegion?.region_code}
          onSelectRegion={handleSelectRegion}
        />

        <MapView
          regions={filteredRegions}
          shelters={shelters}
          showShelters={showShelters}
          onSelectRegion={handleSelectRegion}
          flyTarget={flyTarget}
        />
      </main>

      {selectedRegion && (
        <DetailPanel
          region={selectedRegion}
          onClose={handleCloseDetail}
          onFlyTo={handleFlyTo}
          onShowAreaShelters={handleShowAreaShelters}
        />
      )}
    </div>
  );
}
