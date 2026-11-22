import KeyFramesBrowser from "./KeyFramesBrowser.jsx";

export default function KeyFramesPanel({ job, onSeek }) {
  return (
    <KeyFramesBrowser
      key={job?.id}
      job={job}
      onSeek={onSeek}
    />
  );
}