"""Общие настройки сервиса.

Здесь собраны простые константы: лимиты длительности и разрешения
видео, параметры превью, языки OCR, веса этапов для полосы
прогресса и раскладка файлов задания.

Менять эти значения можно без правки логики этапов.
"""

from pathlib import Path

# ─────────────────────────── модели ──────────────────────────

# Корень пакета app и папка с ONNX-моделями (YOLOv8n и другие).
APP_DIR = Path(__file__).resolve().parent
MODELS_DIR = APP_DIR / "models"

# ─────────────────────────── видео ───────────────────────────

# Верхняя граница длительности. Длинные ролики обрабатываются
# дольше, но именно для них важно много кадров (500+).
MAX_DURATION_SECONDS = 60 * 60
MAX_SOURCE_PIXELS = 4096 * 2160

PREVIEW_WIDTH = 1280
PREVIEW_CRF = 24
PREVIEW_PRESET = "veryfast"

DEFAULT_ANALYSIS_FRAMES = 500
MAX_ANALYSIS_FRAMES = 2000
MIN_FRAME_SPACING_SECONDS = 0.35

OCR_LANGUAGES = ("ru", "en")

# ─────────────────────────── хранилище ───────────────────────
#
# Раскладка (совпадает с текущей в jobs.py, server.py, pipeline.py):
#
#   backend/data/<uuid_hex>/
#       job.json                  ← метаданные задания (пишет jobs.py)
#       original.bin              ← исходное видео (пишет server.py)
#       report.md                 ← Markdown-отчёт
#       prepared/<...>            ← артефакты этапа prepare (preview и т.п.)
#       result/coordinates.json   ← финальный результат (координаты)
#       runs/<run_id>/<...>       ← артефакты конкретного прогона
#
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

JOB_FILENAME = "job.json"
SOURCE_FILENAME = "original.bin"
REPORT_FILENAME = "report.md"

RUNS_SUBDIR = "runs"
PREPARED_SUBDIR = "prepared"
RESULT_SUBDIR = "result"
RESULT_FILENAME = "coordinates.json"

# ─────────────────────────── этапы ───────────────────────────

STAGE_WEIGHTS = {
    "prepare": 3.0,
    "metadata": 3.0,
    "scenes": 5.0,
    "speech": 9.0,
    "audio_structure": 3.0,
    "ocr": 9.0,
    "structure": 3.0,
    "visual_analysis": 22.0,
    "place_profile": 18.0,
    "location_evidence": 8.0,
    "summary": 4.0,
    "video_structure": 3.0,
    "location_prompt": 10.0,
}