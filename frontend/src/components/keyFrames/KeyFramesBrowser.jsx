import { useEffect, useState } from "react";
import { useKeyframeData } from "./hooks/useKeyframeData.js";
import { useRoadEpisodesData } from "./hooks/useRoadEpisodesData.js";
import { usePagination } from "./hooks/usePagination.js";
import { useServerKeyframes } from "./hooks/useServerKeyframes.js";
import RoadEpisodes from "./parts/RoadEpisodes.jsx";
import FramePage from "./parts/FramePage.jsx";
import Pager from "./parts/Pager.jsx";
import ViewToggle from "./parts/ViewToggle.jsx";
import { formatTime } from "../../utils/formatTime.js";
import { FRAMES_PER_PAGE } from "./lib/constants.js";

export default function KeyFramesBrowser({ job, onSeek }) {
  const {
    roads,
    frames,
    ocr,
    speech,
    scenes,
  } = useKeyframeData(job);

  const episodes = useRoadEpisodesData(job);

  const [view, setView] = useState(null);
  const [group, setGroup] = useState(null);
  const [serverPage, setServerPage] = useState(1);

  const live = job?.status === "completed";

  const server = useServerKeyframes(
    job,
    serverPage,
    group,
    live,
  );

  const localPagination = usePagination(
    frames.length,
    FRAMES_PER_PAGE,
  );

  useEffect(() => {
    setGroup(null);
    setServerPage(1);
  }, [job?.id]);

  const serverData = server.data;
  const usingServer = Boolean(
    live
    && serverData
    && Array.isArray(serverData.frames)
    && serverData.total > 0,
  );

  const mode = episodes.length && view !== "frames"
    ? "road"
    : "frames";

  if (!frames.length && !episodes.length && !usingServer) {
    return null;
  }

  const page = usingServer
    ? serverData.page - 1
    : localPagination.page;
  const pageCount = usingServer
    ? serverData.pages
    : localPagination.pageCount;
  const first = usingServer
    ? serverData.offset
    : localPagination.first;
  const last = usingServer
    ? serverData.offset + serverData.frames.length
    : localPagination.last;
  const total = usingServer
    ? serverData.total
    : frames.length;

  const visibleFrames = usingServer
    ? serverData.frames
    : frames.slice(
      localPagination.first,
      localPagination.first + FRAMES_PER_PAGE,
    );

  const changePage = (next) => {
    if (usingServer) {
      setServerPage(next + 1);
    } else {
      localPagination.setPage(next);
    }
  };

  const groups = usingServer
    ? serverData.groups || []
    : [];

  return (
    <section className="panel keyframes-panel">
      <div className="section-row">
        <h2>Ключевые кадры</h2>

        {usingServer && (
          <span className="insight-count">
            {serverData.total} кадр.
          </span>
        )}
      </div>

      <ViewToggle
        episodeCount={episodes.length}
        frameCount={total}
        mode={mode}
        onSelect={setView}
      />

      {mode === "road" ? (
        <RoadEpisodes
          job={job}
          episodes={episodes}
          segments={roads}
          onSeek={onSeek}
        />
      ) : (
        <>
          {groups.length > 1 && (
            <div className="insight-chips kf-groups">
              <button
                className={`insight-chip insight-chip-button${group === null ? " is-active" : ""}`}
                onClick={() => {
                  setGroup(null);
                  setServerPage(1);
                }}
              >
                Все локации
              </button>

              {groups.map((item) => (
                <button
                  className={`insight-chip insight-chip-button${group === item.number ? " is-active" : ""}`}
                  key={item.number}
                  onClick={() => {
                    setGroup(item.number);
                    setServerPage(1);
                  }}
                  title={`${formatTime(item.start)} — ${formatTime(item.end)}`}
                >
                  {formatTime(item.start)}
                  <small>{item.frame_count}</small>
                </button>
              ))}
            </div>
          )}

          <Pager
            label="Страницы ключевых кадров"
            page={page}
            pageCount={pageCount}
            first={first}
            last={last}
            total={total}
            onPage={changePage}
            canGoBack={page > 0}
            canGoForward={page + 1 < pageCount}
          />

          <FramePage
            job={job}
            onSeek={onSeek}
            roads={roads}
            ocr={ocr}
            speech={speech}
            scenes={scenes}
            frames={visibleFrames}
            offset={first}
          />
        </>
      )}
    </section>
  );
}
