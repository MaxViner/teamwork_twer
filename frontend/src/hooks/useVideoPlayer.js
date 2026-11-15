import { useRef, useState } from "react";

export function useVideoPlayer() {
  const videoRef = useRef(null);
  const [currentTime, setCurrentTime] = useState(0);

  const seek = (seconds) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = seconds;
    setCurrentTime(seconds);
  };

  const handleTimeUpdate = (event) => setCurrentTime(event.currentTarget.currentTime);
  return { videoRef, currentTime, seek, handleTimeUpdate };
}
