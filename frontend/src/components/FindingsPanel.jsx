import Finding from "./Finding.jsx";
import FindingsFilters from "./FindingsFilters.jsx";

export default function FindingsPanel({ observations, jobId, busy, search, onSearchChange, sourceFilter, onSourceFilterChange, reviewFilter, onReviewFilterChange, onSeek, onSave, onError }) {
  return (
    <section className="panel findings-panel">
      <h2>Наблюдения</h2>
      <FindingsFilters search={search} onSearchChange={onSearchChange} sourceFilter={sourceFilter} onSourceFilterChange={onSourceFilterChange} reviewFilter={reviewFilter} onReviewFilterChange={onReviewFilterChange} />
      <p className="muted">Найдено: {observations.length}{busy ? " · Исправления доступны после обработки." : ""}</p>
      <div className="findings">
        {observations.map((item) => <Finding key={item.id} item={item} jobId={jobId} busy={busy} onSeek={onSeek} onSave={onSave} onError={onError} />)}
        {!observations.length && <p className="empty">Нет наблюдений для выбранного фильтра.</p>}
      </div>
    </section>
  );
}
