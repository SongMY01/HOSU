import { useState, useEffect, useCallback } from 'react';
import { fetchRegions } from '../api/hosuApi';

export function useRegions(level) {
  const [regions, setRegions] = useState([]);
  const [asOf, setAsOf] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchRegions(level);
      setRegions(data.regions);
      setAsOf(data.as_of);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [level]);

  useEffect(() => { load(); }, [load]);

  return { regions, asOf, loading, error, reload: load };
}
