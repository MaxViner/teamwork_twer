import { SOURCE_LABELS, REVIEW_LABELS, COMBINED_SOURCES } from "../constants/labels.js";

export default function FindingsFilters({ search, onSearchChange, sourceFilter, onSourceFilterChange, reviewFilter, onReviewFilterChange }) {
  return (
    <div className="filters">
      <input placeholder="Поиск по тексту" value={search} onChange={(event) => onSearchChange(event.target.value)} aria-label="Поиск по наблюдениям" />
      <select value={sourceFilter} onChange={(event) => onSourceFilterChange(event.target.value)} aria-label="Источник наблюдения">
        <option value="all">Все источники</option>
        {Object.entries(SOURCE_LABELS).filter(([value]) => !COMBINED_SOURCES.includes(value)).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      <select value={reviewFilter} onChange={(event) => onReviewFilterChange(event.target.value)} aria-label="Статус проверки">
        <option value="all">Любая проверка</option>
        {Object.entries(REVIEW_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
    </div>
  );
}
