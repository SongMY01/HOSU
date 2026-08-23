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
  const [globalShelters, setGlobalShelters] = useState([]);
  const [isAreaMode, setIsAreaMode] = useState(false);
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

  // Load all global shelters (up to 6,000)
  const fetchAllShelters = useCallback(async () => {
    if (globalShelters.length > 0) {
      setShelters(globalShelters);
      return globalShelters;
    }
    try {
      const data = await fetchShelters({ limit: 6000 });
      const list = data.shelters || [];
      setGlobalShelters(list);
      setShelters(list);
      return list;
    } catch (e) {
      console.error('전체 쉼터 로드 실패:', e);
      return [];
    }
  }, [globalShelters]);

  // Toggle shelter layer from Header
  const handleShelterToggle = useCallback(async () => {
    // 1. 관내 쉼터만 띄워진 상태에서 상단 버튼을 누른 경우 -> 전역 전체 쉼터로 전환
    if (showShelters && isAreaMode) {
      setIsAreaMode(false);
      await fetchAllShelters();
      return;
    }

    // 2. 이미 전체 쉼터가 켜진 상태 -> 끄기
    if (showShelters && !isAreaMode) {
      setShowShelters(false);
      return;
    }

    // 3. 꺼진 상태 -> 켜고 전체 쉼터 로드
    setShowShelters(true);
    setIsAreaMode(false);
    await fetchAllShelters();
  }, [showShelters, isAreaMode, fetchAllShelters]);

  // Show specific area shelters from DetailPanel
  const handleShowAreaShelters = useCallback((newShelters, target) => {
    setShelters(newShelters);
    setShowShelters(true);
    setIsAreaMode(true);
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
          summary={summary}
        />
      </main>

      {selectedRegion && (
        <DetailPanel
          region={selectedRegion}
          onClose={handleCloseDetail}
          onFlyTo={handleFlyTo}
          onShowAreaShelters={handleShowAreaShelters}
          summary={summary}
        />
      )}
    </div>
  );
}
