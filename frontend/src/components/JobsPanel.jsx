import Button from "./ui/Button.jsx";
import CollapsiblePanel from "./ui/CollapsiblePanel.jsx";


export default function JobsPanel({ jobs, selectedId, onSelect, onRefresh }) {
  return (
    <CollapsiblePanel
      title="Задания"
      subtitle="Выберите видео, чтобы открыть его анализ."
      actions={<Button onClick={onRefresh}>Обновить список</Button>}
    >
      <select value={selectedId} onChange={(event) => onSelect(event.target.value)}>
        <option value="">Выберите видео</option>
        {jobs.map((job) => <option key={job.id} value={job.id}>{job.name} · {new Date(job.created_at).toLocaleString()}</option>)}
      </select>
    </CollapsiblePanel>
  );
}
