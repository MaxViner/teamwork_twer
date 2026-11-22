// hooks/usePagination.js
import { useState } from "react";

export function usePagination(total, pageSize) {
  const [page, setPage] = useState(0);
  const pageCount = Math.ceil(total / pageSize);

  const current = Math.max(
    0,
    Math.min(page, pageCount - 1),
  );

  const first = current * pageSize;

  return {
    page: current,
    pageCount,
    first,
    last: Math.min(total, first + pageSize),
    setPage,
    canGoBack: current > 0,
    canGoForward: current + 1 < pageCount,
  };
}