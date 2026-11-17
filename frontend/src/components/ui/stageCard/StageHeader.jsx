import {
    STAGE_LABELS,
    STATUS_LABELS,
} from "../../../constants/labels.js";



export default function StageHeader({
    stageKey,
    status,
    percentLabel,
    skipped,
}) {
    return (
        <header className="stage-heading">
            <div>
                <h3>
                    {STAGE_LABELS[stageKey] || stageKey}
                </h3>


                <span className="stage-status-label">
                    {STATUS_LABELS[status] || status}
                </span>
            </div>


            {!skipped && (
                <strong className="stage-percent">
                    {percentLabel}
                </strong>
            )}
        </header>
    );
}