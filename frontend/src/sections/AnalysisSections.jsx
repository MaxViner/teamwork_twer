import LocationDossier from "../components/LocationDossier.jsx";
import MapQueryPanel from "../components/mapQueryPanel/MapQueryPanel.jsx";
import LandmarksPanel from "../components/LandmarksPanel.jsx";
import KeyFramesPanel from "../components/keyFrames/KeyFramesPanel.jsx";
import GeometryPanel from "../components/geometryPanel/GeometryPanel.jsx";
import SummaryPanel from "../components/SummaryPanel.jsx";
import StructurePanel from "../components/StructurePanel.jsx";
import TranscriptPanel from "../components/TranscriptPanel.jsx";
import SearchPanel from "../components/SearchPanel.jsx";
import ComprehensionPanel from "../components/ComprehensionPanel.jsx";
import FacesPanel from "../components/FacesPanel.jsx";

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
}) {
    return (
        <>
            <Section id="section-dossier">
                <LocationDossier job={job} />
            </Section>

            <Section id="section-map-query">
                <MapQueryPanel job={job} onSeek={onSeek} />
            </Section>

            <Section id="section-landmarks">
                <LandmarksPanel job={job} onSeek={onSeek} />
            </Section>

            <Section id="section-keyframes">
                <KeyFramesPanel job={job} onSeek={onSeek} />
            </Section>

            <Section id="section-geometry">
                <GeometryPanel job={job} onSeek={onSeek} />
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

            <Section id="section-search">
                <SearchPanel job={job} onSeek={onSeek} onError={onError} />
            </Section>

            <Section id="section-questions">
                <ComprehensionPanel job={job} onSeek={onSeek} />
            </Section>

            <Section id="section-faces">
                <FacesPanel job={job} onSeek={onSeek} />
            </Section>
        </>
    );
}
