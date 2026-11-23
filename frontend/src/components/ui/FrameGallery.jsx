import { useEffect, useState } from "react";
import { fileUrl } from "../../utils/fileUrl.js";
import { formatTime } from "../../utils/formatTime.js";


const FRAMES_PER_PAGE = 12;


/**
 * Компактная галерея кадров с пагинацией — тот же вид,
 * что в панели «Ориентиры в кадрах».
 */
export default function FrameGallery({
    jobId,
    frames,
    onSeek,
    pageSize = FRAMES_PER_PAGE,
}) {
    const [page, setPage] = useState(1);

    const signature = frames
        .map((frame) => `${frame.artifact}:${frame.timestamp}`)
        .join("|");

    useEffect(() => {
        setPage(1);
    }, [signature]);

    if (!frames.length) {
        return null;
    }

    const pages = Math.max(1, Math.ceil(frames.length / pageSize));
    const current = Math.min(page, pages);
    const offset = (current - 1) * pageSize;
    const visible = frames.slice(offset, offset + pageSize);

    return (
        <>
            <div className="thumb-grid">
                {visible.map((frame, index) => (
                    <button
                        type="button"
                        className="thumb"
                        key={`${frame.artifact}-${offset + index}`}
                        onClick={() => onSeek(frame.timestamp)}
                        title="Перейти к кадру"
                    >
                        <span className="thumb-media">
                            <img
                                src={fileUrl(jobId, frame.artifact)}
                                alt={`Кадр ${formatTime(frame.timestamp)}`}
                                loading="lazy"
                            />

                            <span className="kf-frame-time">
                                {formatTime(frame.timestamp)}
                            </span>
                        </span>

                        {frame.caption && (
                            <span className="thumb-caption">
                                {frame.caption}
                            </span>
                        )}
                    </button>
                ))}
            </div>

            {pages > 1 && (
                <div className="insight-pager">
                    <button
                        type="button"
                        className="insight-page-button"
                        disabled={current <= 1}
                        onClick={() => setPage(current - 1)}
                    >
                        ←
                    </button>

                    <span className="muted">
                        Кадры: {current} / {pages}
                    </span>

                    <button
                        type="button"
                        className="insight-page-button"
                        disabled={current >= pages}
                        onClick={() => setPage(current + 1)}
                    >
                        →
                    </button>
                </div>
            )}
        </>
    );
}
