// "45 min", "2 h", "1 h 30 min" for credited minutes.
export function formatMinutes(total) {
  const minutes = Math.max(0, Math.round(Number(total) || 0));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}
