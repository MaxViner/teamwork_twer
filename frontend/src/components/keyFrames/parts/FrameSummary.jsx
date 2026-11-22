export default function FrameSummary({ road, objects, text }) {
  const summary = [
    road?.direction,
    ...objects.slice(0, 2).map(
      (item) => item.label_ru || item.label,
    ),
    text && `«${text.slice(0, 90)}${text.length > 90 ? "…" : ""}»`,
  ].filter(Boolean).join(" · ");

  return (
    <p
      className="muted"
      style={{
        margin: 0,
        overflowWrap: "anywhere",
      }}
    >
      {summary || "Нет кратких отметок"}
    </p>
  );
}