export const STAGE_LABELS = {
  prepare: "Подготовка",
  metadata: "Метаданные",
  scenes: "Сцены",
  speech: "Речь",
  ocr: "Текст на кадрах",
  visual: "Визуальные признаки",
  audio_events: "Звуковые события",
  structure: "Порядок кадров",
};

export const STATUS_LABELS = {
  pending: "Ожидает",
  queued: "В очереди",
  running: "Выполняется",
  completed: "Готово",
  failed: "Ошибка",
  skipped: "Пропущено",
};

export const STAGE_COUNT_LABELS = {
  prepare: "Техническая сводка",
  metadata: "Метаданные",
  scenes: "Сцены",
  speech: "Реплики речи",
  ocr: "Найдено текстовых фрагментов",
  visual: "Визуальные признаки",
  audio_events: "Звуковые события",
  structure: "Связи кадров",
};

export const STAGE_ORDER = [
  "prepare",
  "metadata",
  "scenes",
  "speech",
  "ocr",
  "visual",
  "audio_events",
  "structure",
];