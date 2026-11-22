export default function RoadDiagram({ geometry }) {
  const rows = geometry?.rows;

  if (!Array.isArray(rows) || rows.length < 2) {
    return null;
  }

  return (
    <svg
      viewBox="0 0 100 100"
      width="78"
      height="58"
      role="img"
      aria-label="Границы и ось видимого дорожного коридора в изображении"
      style={{
        display: "block",
        border: "1px solid currentColor",
        borderRadius: 4,
      }}
    >
      {["left_x", "center_x", "right_x"].map((field) => (
        <polyline
          key={field}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeDasharray={field === "center_x" ? "3 3" : undefined}
          points={rows.map(
            (row) => `${100 * row[field]},${100 * row.y}`,
          ).join(" ")}
        />
      ))}
    </svg>
  );
}