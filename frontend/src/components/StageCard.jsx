import Button from "./ui/Button.jsx";
import { STAGE_LABELS, STATUS_LABELS } from "../constants/labels.js";

export default function StageCard({ stageKey, stage, job, busy, onRetry }) {
  const canRetry = !busy && !(["metadata", "speech", "ocr"].includes(stageKey) && !job.options?.[stageKey]);
  return (
    <article className={`stage status-${stage.status}`}>
      <h3>{STAGE_LABELS[stageKey]}</h3>
      <p>{STATUS_LABELS[stage.status]}</p>
      <small>Находок: {stage.observations?.length || 0}</small>
      {stage.note && <p className="muted">{stage.note}</p>}
      {stage.error && <p className="stage-error">{stage.error}</p>}
      {stage.result_run_id !== stage.run_id && <p className="muted">Показан результат прошлой попытки.</p>}
      <Button disabled={!canRetry} onClick={() => onRetry(stageKey)}>Повторить</Button>
      {stage.history_count > 0 && <small>В истории: {stage.history_count}</small>}
    </article>
  );
}
