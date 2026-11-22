export function roundTime(value) {
  return Math.round(value * 1000) / 1000;
}

export function formatPercent(value) {
  const number = Number(value);

  return Number.isFinite(number) ? `${number}%` : "";
}

export function cleanRoadText(text) {
  return String(text || "")
    .replace(/^Дорога:\s*/i, "")
    .trim();
}

export function rangeLabel(start, end) {
  const first = formatTime(start);
  const last = formatTime(end);

  return first === last ? first : `${first}–${last}`;
}