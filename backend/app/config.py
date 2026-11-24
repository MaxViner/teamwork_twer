"""Общие настройки сервиса.

Здесь собраны простые константы: лимиты длительности и разрешения
видео, параметры превью, языки OCR, веса этапов для полосы
прогресса и раскладка файлов задания.

Менять эти значения можно без правки логики этапов.
"""

from pathlib import Path

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
    "prepare": 4.0,
    "metadata": 4.0,
    "scenes": 8.0,
    "speech": 12.0,
    "audio_structure": 4.0,
    "ocr": 12.0,
    "structure": 4.0,
    "scene_objects": 12.0,
    "faces": 3.0,
    "visual_profile": 8.0,
    "road_geometry": 5.0,
    "location_evidence": 8.0,
    "summary": 5.0,
    "video_structure": 3.0,
    
    "landmarks": 8.0,
    "ai_prompt": 4.0,
}