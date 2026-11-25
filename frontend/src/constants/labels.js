export const COMBINED_SOURCES = [
    "visual_analysis",
    "place_profile",
    "location_prompt",
];



export const STAGE_ORDER = [
    "prepare",
    "metadata",
    "scenes",
    "speech",
    "audio_structure",
    "ocr",
    "structure",
    "visual_analysis",
    "place_profile",
    "location_evidence",
    "summary",
    "video_structure",
    "location_prompt",
];



export const STAGE_LABELS = {
    prepare: "Подготовка",
    metadata: "Метаданные",
    scenes: "Сцены",
    speech: "Распознавание речи",
    audio_structure: "Звуковая структура",
    ocr: "Текст на кадрах",
    structure: "Повторы и связи кадров",
    visual_analysis: "Визуальный анализ",
    place_profile: "Профиль места",
    location_evidence: "Географические улики",
    summary: "Конспект",
    video_structure: "Структура видео",
    location_prompt: "AI-промпт для поиска места",
};



export const STAGE_COUNT_LABELS = {
    prepare: "Техническая сводка",
    metadata: "Метаданных",
    scenes: "Сцен",
    speech: "Реплик речи",
    audio_structure: "Звуковых событий",
    ocr: "Текстовых фрагментов",
    structure: "Повторов",
    visual_analysis: "Уникальных объектов",
    place_profile: "Эпизодов и ориентиров",
    location_evidence: "Географических улик",
    summary: "Тезисов",
    video_structure: "Разделов",
    location_prompt: "Поисковых промптов",
};



export const STATUS_LABELS = {
    pending: "Ожидает",
    queued: "В очереди",
    running: "Выполняется",
    completed: "Готово",
    failed: "Ошибка",
    skipped: "Пропущено",
};



export const REVIEW_LABELS = {
    unreviewed: "Не проверено",
    accepted: "Принято",
    rejected: "Отклонено",
};



export const SOURCE_LABELS = {
    technical: "Техническая информация",
    metadata: "Метаданные",
    scene: "Сцена",
    speech: "Речь",
    ocr: "Текст на кадрах",
    audio_structure: "Звуковая структура",
    audio_event: "Звуковое событие",
    visual: "Визуальные признаки",
    visual_profile: "Визуальный профиль места",
    relation: "Пространственные отношения",
    sequence: "Последовательность",
    reappearance: "Повторы и совпадения",
    scene_objects: "Объекты и признаки места",
    road_geometry: "Геометрия дороги",
    location_evidence: "Географические улики",
    ai_prompt: "AI-промпт",
    visual_analysis: "Визуальный анализ",
    place_profile: "Профиль места",
    location_prompt: "Поисковый промпт",
};
