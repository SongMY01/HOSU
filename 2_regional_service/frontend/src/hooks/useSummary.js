import { useState, useEffect } from 'react';
import { fetchSummary } from '../api/hosuApi';

export function useSummary() {
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    fetchSummary().then(setSummary).catch(console.error);
  }, []);

  return summary;
}
