import RoadEpisodeFilters from "./RoadEpisodeFilters.jsx";
import RoadEpisodeRow from "./RoadEpisodeRow.jsx";
import Pager from "./Pager.jsx";
import { useRoadEpisodes } from "../hooks/useRoadEpisodes.js";
import { usePagination } from "../hooks/usePagination.js";

export default function RoadEpisodes({
  job,
  episodes,
  segments,
  onSeek,
}) {
  const {
    filter,
    withClues,
    openId,
    filtered,
    pageSize,
    changePage,
    changeFilter,
    changeWithClues,
    setOpenId,
  } = useRoadEpisodes(episodes);

  const pagination = usePagination(
    filtered.length,
    pageSize,
  );

  const visibleEpisodes = filtered.slice(
    pagination.first,
    pagination.first + pageSize,
  );

  return (
    <>
      <RoadEpisodeFilters
        filter={filter}
        onFilterChange={changeFilter}
        withClues={withClues}
        onWithCluesChange={changeWithClues}
        shown={filtered.length}
        total={episodes.length}
      />

      <p className="muted">
        Эпизоды объединены по времени, а не по подтверждённым локациям.
        Стороны и схемы показаны в координатах изображения.
      </p>

      {!filtered.length && (
        <p className="muted">
          Нет эпизодов по выбранным фильтрам.
        </p>
      )}

      <Pager
        label="Страницы дорожных эпизодов"
        page={pagination.page}
        pageCount={pagination.pageCount}
        first={pagination.first}
        last={pagination.last}
        total={filtered.length}
        onPage={changePage}
        canGoBack={pagination.canGoBack}
        canGoForward={pagination.canGoForward}
      />

      {visibleEpisodes.map((episode) => (
        <RoadEpisodeRow
          key={episode.id}
          job={job}
          episode={episode}
          segments={segments}
          onSeek={onSeek}
          open={openId === episode.id}
          onToggle={(isOpen) => setOpenId(
            isOpen ? episode.id : null,
          )}
        />
      ))}
    </>
  );
}