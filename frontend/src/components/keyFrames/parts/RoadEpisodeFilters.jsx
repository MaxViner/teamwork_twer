import { BEND_OPTIONS, toolbar } from "../lib/constants.js";

export default function RoadEpisodeFilters({
  filter,
  onFilterChange,
  withClues,
  onWithCluesChange,
  shown,
  total,
}) {
  return (
    <div style={toolbar}>
      <label>
        Видимый изгиб{" "}

        <select
          value={filter}
          onChange={(event) => onFilterChange(event.target.value)}
        >
          {BEND_OPTIONS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>

      <label>
        <input
          type="checkbox"
          checked={withClues}
          onChange={(event) => onWithCluesChange(event.target.checked)}
        />

        Только с ориентирами
      </label>

      <span className="muted">
        {shown} из {total}
      </span>
    </div>
  );
}