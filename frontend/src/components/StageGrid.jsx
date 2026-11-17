import StageCard from "./ui/stageCard/StageCard";


const STAGE_ORDER = [
    "prepare",
    "metadata",
    "scenes",
    "speech",
    "ocr",
    "structure",
    "scene_objects",
    "visual_profile",
    "location_evidence",
    "road_geometry",
    "audio_structure",
    "visual",
    "audio_events",
];


function stagePosition(key) {
    const index = STAGE_ORDER.indexOf(key);


    return index >= 0
        ? index
        : STAGE_ORDER.length;
}



export default function StageGrid({
    job,
    busy,
    onRetry,
}) {
    const stages = Object.entries(
        job?.stages || {},
    ).sort(
        ([first], [second]) => (
            stagePosition(first)
            - stagePosition(second)
        ),
    );


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
            {stages.map(
                ([key, stage]) => (
                    <StageCard
                        key={key}
                        stageKey={key}
                        stage={stage}
                        job={job}
                        busy={busy}
                        onRetry={onRetry}
                    />
                ),
            )}
        </div>
    );
}