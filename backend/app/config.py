"""Общие настройки сервиса.

Здесь собраны простые константы: лимиты длительности и разрешения
видео, параметры превью, языки OCR и веса этапов для полосы
прогресса. Менять эти значения можно без правки логики этапов.
"""
MAX_DURATION_SECONDS = 20 * 60
MAX_SOURCE_PIXELS = 4096 * 2160

PREVIEW_WIDTH = 1280
PREVIEW_CRF = 24
PREVIEW_PRESET = "veryfast"

DEFAULT_ANALYSIS_FRAMES = 500
MAX_ANALYSIS_FRAMES = 2000
MIN_FRAME_SPACING_SECONDS = 0.35

OCR_LANGUAGES = ("ru", "en")

STAGE_WEIGHTS = {
    "prepare": 5.0,
    "metadata": 5.0,
    "scenes": 10.0,
    "speech": 15.0,
    "audio_structure": 5.0,
    "ocr": 15.0,
    "structure": 5.0,
    "scene_objects": 15.0,
    "visual_profile": 10.0,
    "road_geometry": 5.0,
    "location_evidence": 10.0,
}