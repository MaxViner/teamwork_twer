import StageIcon from "./StageIcon.jsx";
import StageHeader from "./StageHeader.jsx";
import StageProgressBar from "./StageProgressBar.jsx";
import StageMessages from "./StageMessages.jsx";
import StageFooter from "./StageFooter.jsx";
import { STAGE_ORDER } from "../../../constants/labels.js";


const OPTIONAL_STAGE_DEFAULTS = {
    metadata: true,
    speech: true,
    ocr: true,
    visual_analysis: true,
    place_profile: true,
    location_evidence: true,
    audio_structure: true,
    structure: true,
    location_prompt: true,
    visual: false,
    audio_events: false,
};



function readPercent(
    stageKey,
    stage,
    job,
) {
    if (stage.status === "completed") {
        return 100;
    }


    if (
        stage.status === "pending"
        || stage.status === "queued"
    ) {
        return 0;
    }


    const raw =
        stage.progress
        ?? job?.stage_progress?.[stageKey];


    if (raw == null) {
        return null;
    }


    const value = Number(raw);


    if (!Number.isFinite(value)) {
        return null;
    }


    return Math.max(
        0,
        Math.min(100, value),
    );
}



function getPercentLabel({
    status,
    percent,
    skipped,
}) {
    if (skipped) {
        return "Не выполнялся";
    }


    if (
        status === "running"
        && (
            percent == null
            || percent === 0
        )
    ) {
        return "Выполняется…";
    }


    if (percent != null) {
        return `${Math.round(percent)}%`;
    }


    return "Процент не получен";
}



export default function StageCard({
    stageKey,
    stage,
    job,
    busy,
    onRetry,
}) {
    const enabled =
        !(stageKey in OPTIONAL_STAGE_DEFAULTS)
        || (
            job?.options?.[stageKey]
            ?? OPTIONAL_STAGE_DEFAULTS[stageKey]
        );


    const canRetry = !busy && enabled;


    const running =
        stage.status === "running";

    const skipped =
        stage.status === "skipped";

    const failed =
        stage.status === "failed";


    const percent = readPercent(
        stageKey,
        stage,
        job,
    );


    const indeterminate =
        running
        && (
            percent == null
            || percent === 0
        );


    const percentLabel = getPercentLabel({
        status: stage.status,
        percent,
        skipped,
    });


    const stageIndex = STAGE_ORDER.indexOf(
        stageKey,
    );


    const displayOrder =
        stageIndex >= 0
            ? stageIndex
            : STAGE_ORDER.length;


    const showPreviousResult =
        stage.result_run_id
        && stage.result_run_id !== stage.run_id;


    return (
        <article
            className={`stage status-${stage.status}`}
            style={{
                order: displayOrder,
            }}
            aria-busy={running}
        >
            <div className="stage-indicator">
                <StageIcon
                    status={stage.status}
                />
            </div>


            <div className="stage-content">
                <StageHeader
                    stageKey={stageKey}
                    status={stage.status}
                    percentLabel={percentLabel}
                    skipped={skipped}
                />


                {!skipped && (
                    <StageProgressBar
                        stageKey={stageKey}
                        percent={percent}
                        indeterminate={indeterminate}
                        percentLabel={percentLabel}
                    />
                )}


                <StageMessages
                    progressMessage={
                        stage.progress_message
                    }
                    note={stage.note}
                    error={stage.error}
                    failed={failed}
                    showPreviousResult={
                        showPreviousResult
                    }
                    skipped={skipped}
                />


                <StageFooter
                    stageKey={stageKey}
                    stage={stage}
                    canRetry={canRetry}
                    onRetry={onRetry}
                />
            </div>
        </article>
    );
}