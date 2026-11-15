# Local Video Evidence

Локальный сервис анализа видео: подготовка превью, метаданные, сцены, речь и OCR.

## Запуск

```bash
pip install fastapi uvicorn pydantic
# также требуются: ffmpeg, ffprobe, exiftool
# и Python-пакеты: faster-whisper, easyocr, scenedetect, pillow

uvicorn app.main:app --reload
```

## Структура

- `app/main.py` — FastAPI-приложение и HTTP-эндпоинты
- `app/pipeline.py` — запуск этапов анализа
- `app/jobs.py` — хранение и изменение заданий
- `app/stages/` — этапы анализа
- `models.py` — Pydantic-модели
