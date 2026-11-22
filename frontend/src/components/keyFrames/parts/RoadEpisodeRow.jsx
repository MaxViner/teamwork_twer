import { useState } from "react";
import { fileUrl } from "../../../utils/fileUrl.js";
import { formatTime } from "../../../utils/formatTime.js";
import { FRAMES_PER_PAGE, IMAGE_SIDES, toolbar } from "../lib/constants.js";
import { rangeLabel } from "../lib/format.js";
import RoadDiagram from "./RoadDiagram.jsx";
import Pager from "./Pager.jsx";
import { usePagination } from "../hooks/usePagination.js";

export default function RoadEpisodeRow({
  episode,
  segments,
  jobId,
  onSeek,
  open,
  onToggle,
}) {
  const pagination = usePagination(
    episode.frameCount,
    FRAMES_PER_PAGE,
  );

  const frames = open && episode.frameCount
    ? segments.slice(
      episode.segmentOffset + pagination.first,
      Math.min(
        episode.segmentEndIndex,
        episode.segmentOffset + pagination.first + FRAMES_PER_PAGE,
      ),
    )
    : [];

  const refs = episode.reference_frames || [];
  const clues = episode.context_clues || [];
  const cover = refs.find((frame) => frame.artifact);

  return (
    <details
      open={open}
      style={{
        padding: "0.5rem 0",
        borderBottom: "1px solid rgba(127,127,127,0.25)",
      }}
    >
      <summary
        style={{ cursor: "pointer" }}
        onClick={(event) => {
          event.preventDefault();
          onToggle(!open);
        }}
      >
        {cover && (
          <img
            src={fileUrl(jobId, cover.artifact)}
            alt=""
            loading="lazy"
            width="72"
            height="42"
            style={{
              objectFit: "cover",
              verticalAlign: "middle",
              marginInline: "0.5rem",
            }}
          />
        )}

        <strong>{rangeLabel(episode.start, episode.end)}</strong>

        {` · ${episode.bend_label || "Геометрия не определена"} · ${episode.frame_count ?? episode.frameCount} кадр.`}

        {clues[0] && (
          <span className="muted">
            {" · "}
            {clues[0].label_ru || clues[0].label}
          </span>
        )}
      </summary>

      {open && (
        <div style={{ margin: "0.6rem 0 0.3rem 1rem" }}>
          {!!refs.length && (
            <div style={toolbar}>
              <span className="muted">Опорные кадры:</span>

              {refs.map((ref) => (
                <button
                  type="button"
                  key={ref.segment_index ?? ref.timestamp}
                  onClick={() => onSeek(ref.timestamp)}
                  title="Перейти к опорному кадру"
                >
                  {formatTime(ref.timestamp)}
                </button>
              ))}
            </div>
          )}

          {!!clues.length && (
            <ul>
              {clues.map((clue, index) => (
                <li
                  key={`${clue.label}-${clue.image_side}-${index}`}
                >
                  <button
                    type="button"
                    onClick={() => onSeek(clue.timestamp)}
                  >
                    {formatTime(clue.timestamp)}
                  </button>

                  {` ${clue.label_ru || clue.label}`}

                  {IMAGE_SIDES[clue.image_side] && (
                    ` — ${IMAGE_SIDES[clue.image_side]}`
                  )}
                </li>
              ))}
            </ul>
          )}

          {!episode.frameCount && (
            <p className="muted">
              Нет доступных кадров этого эпизода.
            </p>
          )}

          <Pager
            label="Страницы кадров эпизода"
            page={pagination.page}
            pageCount={pagination.pageCount}
            first={pagination.first}
            last={pagination.last}
            total={episode.frameCount}
            onPage={pagination.setPage}
            canGoBack={pagination.canGoBack}
            canGoForward={pagination.canGoForward}
          />

          <div
            style={{
              display: "grid",
              gap: "0.5rem",
              gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 12rem), 1fr))",
            }}
          >
            {frames.map((frame, index) => (
              <article key={episode.segmentOffset + pagination.first + index}>
                <button
                  type="button"
                  className="keyframe-thumb"
                  onClick={() => onSeek(frame.start)}
                >
                  {frame.artifact && (
                    <img
                      src={fileUrl(jobId, frame.artifact)}
                      alt={`Кадр ${formatTime(frame.start)}`}
                      loading="lazy"
                    />
                  )}

                  <span
                    className="keyframe-time"
                    style={frame.artifact ? undefined : { position: "static" }}
                  >
                    {formatTime(frame.start)}
                  </span>
                </button>

                <div style={toolbar}>
                  <RoadDiagram geometry={frame.image_geometry} />

                  <small>
                    {frame.direction || "Геометрия не определена"}
                  </small>
                </div>
              </article>
            ))}
          </div>
        </div>
      )}
    </details>
  );
}