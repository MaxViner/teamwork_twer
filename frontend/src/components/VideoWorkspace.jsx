import VideoPlayer from "./VideoPlayer.jsx";
import Timeline from "./Timeline.jsx";
import FrameGrid from "./FrameGrid.jsx";

export default function VideoWorkspace({ job, observations, currentTime, videoRef, onSeek, onTimeUpdate }) {
  const prepared = job?.stages?.prepare?.result;
  const preview = prepared?.preview;
  const duration = prepared?.duration || 0;
  const frames = job?.stages?.ocr?.result?.frames || [];
  const sceneIntervals = job?.stages?.scenes?.result?.intervals || [];

  return (
    <section className="panel player-panel">
      <h2>Видео и временная шкала</h2>
      {preview ? (
        <>
          <VideoPlayer jobId={job.id} preview={preview} duration={duration} currentTime={currentTime} videoRef={videoRef} onSeek={onSeek} onTimeUpdate={onTimeUpdate} />
          <Timeline observations={observations} sceneIntervals={sceneIntervals} duration={duration} onSeek={onSeek} />
          <p className="muted">Метки: речь — коричневые, OCR — зелёные, сцены — серые. Таймкоды приблизительные.</p>
        </>
      ) : <p className="muted">Видео появится после подготовки.</p>}
      {frames.length > 0 && <FrameGrid jobId={job.id} frames={frames} onSeek={onSeek} />}
    </section>
  );
}
