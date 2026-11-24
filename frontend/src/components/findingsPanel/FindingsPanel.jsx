import Finding from "./Finding.jsx";
import FindingsFilters from "./FindingsFilters.jsx";
import CollapsiblePanel from "../ui/CollapsiblePanel.jsx";


export default function FindingsPanel({ observations, jobId, busy, search, onSearchChange, sourceFilter, onSourceFilterChange, reviewFilter, onReviewFilterChange, onSeek, onSave, onError }) {
  return (
    <CollapsiblePanel
      title="Все наблюдения"
      subtitle={`Найдено: ${observations.length}`}
      className="findings-panel"
    >
      <FindingsFilters search={search} onSearchChange={onSearchChange} sourceFilter={sourceFilter} onSourceFilterChange={onSourceFilterChange} reviewFilter={reviewFilter} onReviewFilterChange={onReviewFilterChange} />
      {busy && <p className="muted">Исправления доступны после обработки.</p>}
      <div className="findings">
        {observations.map((item) => <Finding key={item.id} item={item} jobId={jobId} busy={busy} onSeek={onSeek} onSave={onSave} onError={onError} />)}
        {!observations.length && <p className="empty">Нет наблюдений для выбранного фильтра.</p>}
      </div>
    </CollapsiblePanel>
  );
}
