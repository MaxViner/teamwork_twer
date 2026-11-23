import VideoPlayer from "./VideoPlayer.jsx";
import Timeline from "./Timeline.jsx";

export default function VideoWorkspace({ job, observations, currentTime, videoRef, onSeek, onTimeUpdate }) {
  const prepared = job?.stages?.prepare?.result;
  const preview = prepared?.preview;
  const duration = prepared?.duration || 0;
  const sceneIntervals = job?.stages?.scenes?.result?.intervals || [];
  const speechSegments = job?.stages?.speech?.result?.segments || [];

  return (
    <section className="panel player-panel">
      <h2>Видео — всегда в кадре</h2>
      {preview ? (
        <>
          <VideoPlayer jobId={job.id} preview={preview} duration={duration} currentTime={currentTime} videoRef={videoRef} onSeek={onSeek} onTimeUpdate={onTimeUpdate} />
          <Timeline observations={observations} speechSegments={speechSegments} sceneIntervals={sceneIntervals} duration={duration} onSeek={onSeek} />
          <p className="muted">Метки: речь — коричневые, OCR — зелёные, сцены — серые. Таймкоды приблизительные.</p>
        </>
      ) : <p className="muted">Видео появится после подготовки.</p>}
    </section>
  );
}
