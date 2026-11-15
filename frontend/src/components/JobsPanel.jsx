import Button from "./ui/Button.jsx";

export default function JobsPanel({ jobs, selectedId, onSelect, onRefresh }) {
  return (
    <section className="panel">
      <div className="section-row"><h2>Задания</h2><Button onClick={onRefresh}>Обновить список</Button></div>
      <select value={selectedId} onChange={(event) => onSelect(event.target.value)}>
        <option value="">Выберите видео</option>
        {jobs.map((job) => <option key={job.id} value={job.id}>{job.name} · {new Date(job.created_at).toLocaleString()}</option>)}
      </select>
    </section>
  );
}
