import Button from "../ui/Button.jsx";

import { STAGE_COUNT_LABELS } from "../../constants/labels.js";


export default function StageFooter({
  stageKey,
  stage,
  canRetry,
  onRetry,
}) {
  const count = stage.observations?.length || 0;
  const countLabel =
    STAGE_COUNT_LABELS[stageKey] || "Наблюдений";

  return (
    <footer className="stage-footer">
      <div className="stage-counts">
        <span>
          {countLabel}: {count}
        </span>

        {stage.history_count > 0 && (
          <span>
            В истории: {stage.history_count}
          </span>
        )}
      </div>

      <Button
        disabled={!canRetry}
        onClick={() => onRetry(stageKey)}
      >
        Повторить
      </Button>
    </footer>
  );
}