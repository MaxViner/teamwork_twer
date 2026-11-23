import { useCallback, useRef, useState } from "react";

const TIME_UPDATE_STEP = 0.25;

export function useVideoPlayer() {
    const videoRef = useRef(null);
    const [currentTime, setCurrentTime] = useState(0);
    const lastEmitted = useRef(0);

    const seek = useCallback((seconds) => {
        const video = videoRef.current;

        if (!video) {
            return;
        }

        video.currentTime = seconds;
        setCurrentTime(seconds);
        lastEmitted.current = seconds;
    }, []);

    const handleTimeUpdate = useCallback((event) => {
        const time = event.currentTarget.currentTime;

        if (Math.abs(time - lastEmitted.current) < TIME_UPDATE_STEP) {
            return;
        }

        lastEmitted.current = time;
        setCurrentTime(time);
    }, []);

    return {
        videoRef,
        currentTime,
        seek,
        handleTimeUpdate,
    };
}