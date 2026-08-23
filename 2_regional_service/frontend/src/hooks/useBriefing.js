import { useState, useEffect } from 'react';
import { fetchBriefing } from '../api/hosuApi';

export function useBriefing() {
  const [briefing, setBriefing] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchBriefing()
      .then(setBriefing)
      .catch(() => setBriefing({ text: '브리핑을 불러오지 못했습니다.', source: 'error' }))
      .finally(() => setLoading(false));
  }, []);

  return { briefing, loading };
}
