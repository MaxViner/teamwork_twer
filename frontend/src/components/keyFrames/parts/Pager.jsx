import { toolbar } from "../lib/constants.js";

export default function Pager({
  label,
  page,
  pageCount,
  first,
  last,
  total,
  onPage,
  canGoBack,
  canGoForward,
}) {
  if (pageCount <= 1) {
    return null;
  }

  return (
    <nav
      aria-label={label}
      style={{ ...toolbar, margin: "0.65rem 0" }}
    >
      <button
        type="button"
        disabled={!canGoBack}
        onClick={() => onPage(page - 1)}
      >
        Назад
      </button>

      <span className="muted" aria-live="polite">
        {page + 1} / {pageCount}
        {" · "}
        {first + 1}–{last} из {total}
      </span>

      <button
        type="button"
        disabled={!canGoForward}
        onClick={() => onPage(page + 1)}
      >
        Вперёд
      </button>
    </nav>
  );
}