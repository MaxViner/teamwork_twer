import { STAGE_LABELS } from "../../../constants/labels.js";


export default function StageProgressBar({
    stageKey,
    percent,
    indeterminate,
    percentLabel,
}) {
    const value =
        indeterminate || percent == null
            ? null
            : Math.max(0, Math.min(100, percent));


    return (
        <div
            className={
                "stage-progress-bar"
                + (value == null ? " is-indeterminate" : "")
            }
            role="progressbar"
            aria-label={`Прогресс: ${
                STAGE_LABELS[stageKey]
                || stageKey
            }`}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={
                value == null
                    ? undefined
                    : Math.round(value)
            }
            aria-valuetext={percentLabel}
        >
            <span
                className="stage-progress-fill"
                style={
                    value == null
                        ? undefined
                        : { width: `${value}%` }
                }
            />
        </div>
    );
}
