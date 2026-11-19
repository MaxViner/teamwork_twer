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


    if (stageKey === "scene_objects") {
        if (typeof stage.result?.object_count === "number") {
            return stage.result.object_count;
        }


        if (Array.isArray(stage.result?.unique_objects)) {
            return stage.result.unique_objects.length;
        }


        if (Array.isArray(stage.result?.frames)) {
            const labels = new Set();

            for (const frame of stage.result.frames) {
                for (const item of frame.objects || []) {
                    if (item.label) {
                        labels.add(item.label);
                    }
                }
            }

            if (labels.size) {
                return labels.size;
            }
        }


        return stage.observations?.length ?? 0;
    }


    if (stageKey === "visual_profile") {
        return (
            stage.result?.segment_count
            ?? stage.result?.profile?.sampled_frames
            ?? stage.observations?.length
            ?? 0
        );
    }


    if (stageKey === "road_geometry") {
        return (
            stage.result?.detected_frames
            ?? stage.observations?.length
            ?? 0
        );
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