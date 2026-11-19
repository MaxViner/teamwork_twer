export const COMBINED_SOURCES = [
    "scene_objects",
    "visual_profile",
    "road_geometry",
];



export const STAGE_ORDER = [
    "prepare",
    "metadata",
    "scenes",
    "speech",
    "audio_structure",
    "ocr",
    "structure",
    "scene_objects",
    "visual_profile",
    "road_geometry",
    "location_evidence",
];



export const STAGE_LABELS = {
    prepare: "Подготовка",
    metadata: "Метаданные",
    scenes: "Сцены",
    speech: "Распознавание речи",
    audio_structure: "Звуковая структура",
    ocr: "Текст на кадрах",
    structure: "Повторы и связи кадров",
    scene_objects: "Объекты и признаки места",
    visual_profile: "Визуальный профиль места",
    road_geometry: "Геометрия дороги",
    location_evidence: "Географические улики",
};



export const STAGE_COUNT_LABELS = {
    prepare: "Техническая сводка",
    metadata: "Метаданных",
    scenes: "Сцен",
    speech: "Реплик речи",
    audio_structure: "Звуковых событий",
    ocr: "Текстовых фрагментов",
    structure: "Повторов",
    scene_objects: "Уникальных объектов",
    visual_profile: "Проанализированных кадров",
    road_geometry: "Участков с геометрией дороги",
    location_evidence: "Географических улик",
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
};