const BASE = '';

export async function fetchRegions(level = 'all') {
  const res = await fetch(`${BASE}/api/regions?level=${level}`);
  if (!res.ok) throw new Error('regions fetch failed');
  return res.json(); // { as_of, count, regions: [] }
}

export async function fetchSummary() {
  const res = await fetch(`${BASE}/api/summary`);
  if (!res.ok) throw new Error('summary fetch failed');
  return res.json();
}

export async function fetchBriefing() {
  const res = await fetch(`${BASE}/api/briefing`);
  if (!res.ok) throw new Error('briefing fetch failed');
  return res.json(); // { text, source, model?, error? }
}

export async function fetchShelters({ sigungu, q, limit = 2000 } = {}) {
  const params = new URLSearchParams({ limit });
  if (sigungu) params.append('sigungu', sigungu);
  if (q) params.append('q', q);
  const res = await fetch(`${BASE}/api/shelters?${params}`);
  if (!res.ok) throw new Error('shelters fetch failed');
  return res.json(); // { count, shelters: [] }
}
