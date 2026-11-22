import { useState } from "react";
import { useKeyframeData } from "./hooks/useKeyframeData.js";
import { useRoadEpisodesData } from "./hooks/useRoadEpisodesData.js";
import { usePagination } from "./hooks/usePagination.js";
import RoadEpisodes from "./parts/RoadEpisodes.jsx";
import FramePage from "./parts/FramePage.jsx";
import Pager from "./parts/Pager.jsx";
import ViewToggle from "./parts/ViewToggle.jsx";
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

  const pagination = usePagination(
    frames.length,
    FRAMES_PER_PAGE,
  );

  const mode = episodes.length && view !== "frames"
    ? "road"
    : "frames";

  if (!frames.length && !episodes.length) {
    return null;
  }

  const visibleFrames = frames.slice(
    pagination.first,
    pagination.first + FRAMES_PER_PAGE,
  );

  return (
    <section className="panel keyframes-panel">
      <div className="section-row">
        <h2>Ключевые кадры</h2>
      </div>

      <ViewToggle
        episodeCount={episodes.length}
        frameCount={frames.length}
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
          <Pager
            label="Страницы ключевых кадров"
            page={pagination.page}
            pageCount={pagination.pageCount}
            first={pagination.first}
            last={pagination.last}
            total={frames.length}
            onPage={pagination.setPage}
            canGoBack={pagination.canGoBack}
            canGoForward={pagination.canGoForward}
          />

          <FramePage
            job={job}
            onSeek={onSeek}
            roads={roads}
            ocr={ocr}
            speech={speech}
            scenes={scenes}
            frames={visibleFrames}
            offset={pagination.first}
          />
        </>
      )}
    </section>
  );
}