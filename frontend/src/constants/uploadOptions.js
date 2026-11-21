export const DEFAULT_UPLOAD_OPTIONS = {
    metadata: true,
    speech: true,
    audio_structure: true,
    ocr: true,
    structure: true,
    scene_objects: true,
    visual_profile: true,
    road_geometry: true,
    location_evidence: true,
    summary: true,
    video_structure: true,
    comprehension: true,
    landmarks: true,


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
        name: "scene_objects",
        title: "Определять объекты и признаки места",
        description: "Находит дорогу, здания, деревья, воду и другие видимые элементы сцены.",
    },


    {
        name: "visual_profile",
        title: "Строить визуальный профиль места",
        description: "Оценивает освещённость, погоду, сезон и тип ландшафта по кадрам.",
    },


    {
        name: "road_geometry",
        title: "Определять геометрию дороги",
        description: "Оценивает направление и изгиб видимой дороги для будущего сопоставления с картой.",
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
        name: "comprehension",
        title: "Готовить вопросы по содержанию",
        description: "Строит вопросы и ответы по фактам видео для проверки понимания.",
    },


    {
        name: "landmarks",
        title: "Определять ориентиры и геометрию кадров",
        description: "Ищет церкви, памятники, башни и дома, оценивает горизонт и точку схода для сопоставления с картой.",
    },
];