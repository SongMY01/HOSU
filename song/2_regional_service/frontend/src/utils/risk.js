export function riskColor(s) {
  if (s >= 75) return '#ef4444';
  if (s >= 55) return '#f97316';
  if (s >= 35) return '#f59e0b';
  return '#10b981';
}

export function riskClass(s) {
  if (s >= 75) return 'crit';
  if (s >= 55) return 'high';
  if (s >= 35) return 'mid';
  return 'low';
}

export function riskGrade(s) {
  if (s >= 75) return '매우 높음';
  if (s >= 55) return '높음';
  if (s >= 35) return '보통';
  return '낮음';
}
