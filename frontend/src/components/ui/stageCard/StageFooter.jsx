import Button from "../../ui/Button.jsx";


import { STAGE_COUNT_LABELS } from "../../../constants/labels.js";



function stageCount(stageKey, stage) {
    if (stageKey === "speech") {
        return (
            stage.result?.segment_count
            ?? stage.observations?.length
            ?? 0
        );
    }


    if (stageKey === "scenes") {
        return (
            stage.result?.scene_count
            ?? stage.result?.intervals?.length
            ?? stage.observations?.length
            ?? 0
        );
    }


    if (stageKey === "audio_structure") {
        return (
            stage.result?.event_count
            ?? stage.observations?.length
            ?? 0
        );
    }


    if (stageKey === "visual_analysis") {
        return (
            stage.result?.object_count
            ?? stage.result?.unique_objects?.length
            ?? stage.result?.counts?.frames
            ?? stage.observations?.length
            ?? 0
        );
    }


    if (stageKey === "place_profile") {
        return (
            stage.result?.road?.summary?.detected_frames
            ?? stage.result?.landmark_count
            ?? stage.observations?.length
            ?? 0
        );
    }


    if (stageKey === "location_prompt") {
        return stage.result?.prompt ? 1 : 0;
    }


    return stage.observations?.length || 0;
}



export default function StageFooter({
    stageKey,
    stage,
    canRetry,
    onRetry,
}) {
    const count = stageCount(
        stageKey,
        stage,
    );


    const countLabel =
        STAGE_COUNT_LABELS[stageKey]
        || "Наблюдений";


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