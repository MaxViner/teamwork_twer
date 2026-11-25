import CollapsiblePanel from "../../ui/CollapsiblePanel.jsx";
import TranscriptPanel from "./TranscriptPanel.jsx";
import SoundPanel from "./SoundPanel.jsx";
import "./audio-analysis.css";


export default function AudioAnalysisPanel({ job, onSeek }) {
    const speech = job?.stages?.speech;
    const audio = job?.stages?.audio_structure;

    if (!speech && !audio) {
        return null;
    }

    const transcriptCount = speech?.result?.segments?.length || 0;
    const soundCount = (audio?.result?.sound_summary || [])
        .reduce((sum, item) => sum + (item.count || 0), 0);

    const parts = [];
    if (transcriptCount > 0) parts.push(`${transcriptCount} реплик`);
    if (soundCount > 0) parts.push(`${soundCount} звуков`);

    return (
        <CollapsiblePanel
            title="Аудиальный анализ"
            subtitle={parts.join(" · ")}
            className="audio-section"
        >
            {transcriptCount > 0 && (
                <div className="audio-section__block">
                    <h3 className="audio-section__heading">Речь</h3>
                    <TranscriptPanel job={job} onSeek={onSeek} embedded />
                </div>
            )}

            {audio && transcriptCount > 0 && (
                <div className="audio-section__divider" aria-hidden="true" />
            )}

            {audio && (
                <div className="audio-section__block">
                    <h3 className="audio-section__heading">
                        Звуки и акустика места
                    </h3>
                    <SoundPanel job={job} onSeek={onSeek} embedded />
                </div>
            )}
        </CollapsiblePanel>
    );
}
