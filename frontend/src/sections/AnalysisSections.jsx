import LocationDossier from "../components/LocationDossier.jsx";
import LocationPromptPanel from "../components/locationPromptPanel/LocationPromptPanel.jsx";
import MapQueryPanel from "../components/mapQueryPanel/MapQueryPanel.jsx";
import KeyFramesPanel from "../components/keyFrames/KeyFramesPanel.jsx";
import PlaceProfilePanel from "../components/placeProfilePanel/PlaceProfilePanel.jsx";
import SummaryPanel from "../components/SummaryPanel.jsx";
import StructurePanel from "../components/StructurePanel.jsx";
import TranscriptPanel from "../components/TranscriptPanel.jsx";
import VisualAnalysisPanel from "../components/visualAnalysisPanel/VisualAnalysisPanel.jsx";

function Section({ id, children }) {
    return (
        <section id={id} className="section-anchor-wrap">
            {children}
        </section>
    );
}

export default function AnalysisSections({
    job,
    onSeek,
    onError,
    onRetry,
}) {
    return (
        <>
            <Section id="section-visual-analysis">
                <VisualAnalysisPanel job={job} onSeek={onSeek} />
            </Section>

            <Section id="section-place-profile">
                <PlaceProfilePanel job={job} onSeek={onSeek} />
            </Section>

            <Section id="section-keyframes">
                <KeyFramesPanel job={job} onSeek={onSeek} />
            </Section>

            <Section id="section-summary">
                <SummaryPanel job={job} onSeek={onSeek} />
            </Section>

            <Section id="section-structure">
                <StructurePanel job={job} onSeek={onSeek} />
            </Section>

            <Section id="section-transcript">
                <TranscriptPanel job={job} onSeek={onSeek} />
            </Section>

            <Section id="section-map-query">
                <MapQueryPanel job={job} onSeek={onSeek} />
            </Section>

            <Section id="section-dossier">
                <LocationDossier job={job} />
            </Section>

            <Section id="section-location-prompt">
                <LocationPromptPanel job={job} onRetry={onRetry} />
            </Section>
        </>
    );
}
