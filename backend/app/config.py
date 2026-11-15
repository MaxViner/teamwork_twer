MAX_DURATION_SECONDS = 20 * 60
MAX_SOURCE_PIXELS = 4096 * 2160

PREVIEW_WIDTH = 1280
PREVIEW_CRF = 24
PREVIEW_PRESET = "veryfast"

OCR_LANGUAGES = ("ru", "en")

STAGE_WEIGHTS = {
    "prepare": 45,
    "metadata": 2,
    "scenes": 8,
    "speech": 25,
    "ocr": 20,
}