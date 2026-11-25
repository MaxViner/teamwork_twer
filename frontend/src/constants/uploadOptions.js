export const DEFAULT_UPLOAD_OPTIONS = {
    metadata: true,
    speech: true,
    audio_structure: true,
    ocr: true,
    structure: true,
    visual_analysis: true,
    place_profile: true,
    location_evidence: true,
    summary: true,
    video_structure: true,
    location_prompt: true,


    language: null,
    max_frames: 500,
    whisper_model: "small",
};



export const UPLOAD_TOGGLES = [
    {
        name: "metadata",
        title: "Читать GPS и метаданные",
        description: "Извлекает координаты, время съёмки и технические данные файла.",
    },


    {
        name: "speech",
        title: "Распознавать речь",
        description: "Преобразует речь в текст и ищет упоминания места.",
    },


    {
        name: "audio_structure",
        title: "Анализировать звуковую структуру",
        description: "Находит тишину и заметно громкие участки. Не распознаёт конкретные звуки.",
    },


    {
        name: "ocr",
        title: "Искать текст на кадрах",
        description: "Читает вывески, таблички, экраны и другие видимые надписи.",
    },


    {
        name: "structure",
        title: "Искать повторяющиеся кадры",
        description: "Находит визуально похожие кадры и возможные повторы сцен.",
    },


    {
        name: "visual_analysis",
        title: "Анализировать кадры",
        description: "Метрики, семантика SegFormer, объекты YOLOv8n и анонимные лица за один проход.",
    },


    {
        name: "place_profile",
        title: "Строить профиль места",
        description: "Дорога, геометрия кадров, ориентиры, одометрия и топологическая BEV-карта.",
    },


    {
        name: "location_evidence",
        title: "Искать место съёмки",
        description: "Собирает GPS, адреса, бренды, язык и визуальный профиль в досье со страной и местами-кандидатами.",
    },


    {
        name: "summary",
        title: "Составлять конспект",
        description: "Выделяет темы, тезисы и выводы по речи, надписям и объектам.",
    },


    {
        name: "video_structure",
        title: "Делить видео на разделы",
        description: "Создаёт автоматические таймкоды с названиями разделов для навигации.",
    },


    {
        name: "location_prompt",
        title: "Формировать поисковый промпт",
        description: "AI собирает накопленные улики в готовое задание для геолокатора. Требует настроенного AI-провайдера.",
    },
];
