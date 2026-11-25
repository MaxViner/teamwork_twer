import { Section } from "../components/ui/Section.jsx";

import MapQueryPanel from "../components/mapQueryPanel/MapQueryPanel.jsx";
import KeyFramesPanel from "../components/keyFrames/KeyFramesPanel.jsx";
import PlaceProfilePanel from "../components/placeProfilePanel/PlaceProfilePanel.jsx";
import LocationDossier from "../components/LocationDossier.jsx";
import LocationPromptPanel from "../components/locationPromptPanel/LocationPromptPanel.jsx";

import VisualAnalysisPanel from "../components/panels/visualAnalysisPanel/VisualAnalysisPanel.jsx";
import AudioAnalysisPanel from "../components/panels/audioAnalysisPanel/AudioAnalysisPanel.jsx";
import SummaryPanel from "../components/panels/summaryPanel/SummaryPanel.jsx";
import StructurePanel from "../components/panels/structurePanel/StructurePanel.jsx";


export default function AnalysisSections({
    job,
    onSeek,
    onError,
    onRetry,
}) {
    return (
        <>
            {/* Визуальные признаки: сцены, текст на кадрах, объекты,
                сегментация и лица — одна панель. */}
            <Section id="section-visual-analysis">
                <VisualAnalysisPanel job={job} onSeek={onSeek} />
            </Section>

            {/* Речь и акустические признаки места — одна панель. */}
            <Section id="section-audio-analysis">
                <AudioAnalysisPanel job={job} onSeek={onSeek} />
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
