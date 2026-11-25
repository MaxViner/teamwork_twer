import VideoWorkspace from "../components/videoWorkspace/VideoWorkspace.jsx";
import AnalysisSections from "./AnalysisSections.jsx";

export default function InspectionShell({
    job,
    observations,
    video,
    onError,
    onRetry,
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
                <AnalysisSections
                    job={job}
                    onSeek={video.seek}
                    onError={onError}
                    onRetry={onRetry}
                />
            </div>
        </div>
    );
}
