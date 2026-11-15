import StageCard from "./StageCard.jsx";

export default function StageGrid({ job, busy, onRetry }) {
  return (
    <div className="stage-grid">
      {Object.entries(job?.stages || {}).map(([key, stage]) => (
        <StageCard key={key} stageKey={key} stage={stage} job={job} busy={busy} onRetry={onRetry} />
      ))}
    </div>
  );
}
