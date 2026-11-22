// hooks/useRoadEpisodes.js
import { useMemo, useState } from "react";
import { EPISODES_PER_PAGE } from "../lib/constants.js";

export function useRoadEpisodes(episodes) {
  const [filter, setFilter] = useState("all");
  const [withClues, setWithClues] = useState(false);
  const [page, setPage] = useState(0);
  const [openId, setOpenId] = useState(null);

  const filtered = useMemo(
    () => episodes.filter((episode) =>
      (filter === "all" || episode.bend_class === filter)
      && (!withClues || episode.context_clues?.length),
    ),
    [episodes, filter, withClues],
  );

  const changePage = (next) => {
    setPage(next);
    setOpenId(null);
  };

  const resetFilters = () => changePage(0);

  return {
    filter,
    setFilter: (value) => {
      setFilter(value);
      resetFilters();
    },
    withClues,
    setWithClues: (value) => {
      setWithClues(value);
      resetFilters();
    },
    page,
    changePage,
    openId,
    setOpenId,
    filtered,
    pageSize: EPISODES_PER_PAGE,
  };
}