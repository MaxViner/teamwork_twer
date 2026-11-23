import VideoWorkspace from "../components/videoWorkspace/VideoWorkspace.jsx";
import AnalysisSections from "./AnalysisSections.jsx";
import FindingsPanel from "../components/findingsPanel/FindingsPanel.jsx";

export default function InspectionShell({
    job,
    observations,
    visible,
    busy,
    filters,
    video,
    onSave,
    onError,
}) {
    return (
        <div className="inspection-shell">
            <aside className="inspection-shell__video" aria-label="Инспектируемое видео">
                <VideoWorkspace
                    job={job}
                    observations={observations}
                    currentTime={video.currentTime}
                    videoRef={video.videoRef}
                    onSeek={video.seek}
                    onTimeUpdate={video.handleTimeUpdate}
                />
            </aside>

            <div className="inspection-shell__content">
                <section id="section-observations" className="section-anchor-wrap">
                    <FindingsPanel
                        observations={visible}
                        jobId={job.id}
                        busy={busy}
                        search={filters.search}
                        onSearchChange={filters.setSearch}
                        sourceFilter={filters.sourceFilter}
                        onSourceFilterChange={filters.setSourceFilter}
                        reviewFilter={filters.reviewFilter}
                        onReviewFilterChange={filters.setReviewFilter}
                        onSeek={video.seek}
                        onSave={onSave}
                        onError={onError}
                    />
                </section>
                <AnalysisSections job={job} onSeek={video.seek} onError={onError} />
            </div>
        </div>
    );
}
