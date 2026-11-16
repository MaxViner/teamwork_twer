import StageCard from "./ui/stageCard/StageCard.jsx";


const STAGE_ORDER = [
  "prepare",
  "metadata",
  "scenes",
  "speech",
  "ocr",
  "visual",
  "audio_events",
  "structure",
];


function stagePosition(key) {
  const index = STAGE_ORDER.indexOf(key);

  // Неизвестные новые этапы показываем в конце.
  return index >= 0 ? index : STAGE_ORDER.length;
}


export default function StageGrid({
  job,
  busy,
  onRetry,
}) {
  const stages = Object.entries(job?.stages || {})
    .sort(([first], [second]) => (
      stagePosition(first) - stagePosition(second)
    ));

  if (stages.length === 0) {
    return (
      <p className="muted">
        Этапы обработки пока отсутствуют.
      </p>
    );
  }

  return (
    <div
      className="stage-grid"
      aria-label="Этапы обработки видео"
    >
      {stages.map(([key, stage]) => (
        <StageCard
          key={key}
          stageKey={key}
          stage={stage}
          job={job}
          busy={busy}
          onRetry={onRetry}
        />
      ))}
    </div>
  );
}