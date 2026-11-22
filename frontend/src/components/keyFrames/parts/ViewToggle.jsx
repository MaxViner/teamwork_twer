import { toolbar } from "../lib/constants.js";

export default function ViewToggle({
  episodeCount,
  frameCount,
  mode,
  onSelect,
}) {
  return (
    <div
      role="group"
      aria-label="Показать"
      style={toolbar}
    >
      {!!episodeCount && (
        <button
          type="button"
          aria-pressed={mode === "road"}
          onClick={() => onSelect("road")}
        >
          Дорожные эпизоды ({episodeCount})
        </button>
      )}

      <button
        type="button"
        aria-pressed={mode === "frames"}
        onClick={() => onSelect("frames")}
      >
        Все кадры ({frameCount})
      </button>
    </div>
  );
}