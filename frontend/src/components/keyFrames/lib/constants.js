export const FRAMES_PER_PAGE = 12;
export const EPISODES_PER_PAGE = 8;

export const SPEECH_WINDOW_SECONDS = 10;
export const SPEECH_LIMIT = 5;

export const ROAD_MATCH_TOLERANCE_SECONDS = 0.2;

export const ROAD_SEMANTIC_LABELS = [
  "road",
  "path",
  "bridge",
];

export const ROAD_SEMANTIC_MIN_PERCENT = 1;

export const BEND_OPTIONS = [
  ["all", "Все изгибы"],
  ["left", "Влево"],
  ["right", "Вправо"],
  ["straight", "Прямой участок"],
  ["uncertain", "Неоднозначно"],
];

export const IMAGE_SIDES = {
  left: "слева в кадре",
  right: "справа в кадре",
  image_overlap: "перекрывает коридор в кадре",
};

export const toolbar = {
  display: "flex",
  gap: "0.65rem",
  alignItems: "center",
  flexWrap: "wrap",
};