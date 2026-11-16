import { STAGE_LABELS } from "../../../constants/labels.js";


export default function StageProgressBar({
  stageKey,
  percent,
  indeterminate,
  percentLabel,
}) {
  const value =
    indeterminate || percent == null
      ? undefined
      : percent;

  return (
    <progress
      className="stage-progress-bar"
      max={100}
      value={value}
      aria-label={`Прогресс: ${STAGE_LABELS[stageKey] || stageKey}`}
      aria-valuetext={percentLabel}
    />
  );
}