MAX_DURATION_SECONDS = 20 * 60
MAX_SOURCE_PIXELS = 4096 * 2160

PREVIEW_WIDTH = 1280
PREVIEW_CRF = 24
PREVIEW_PRESET = "veryfast"

OCR_LANGUAGES = ("ru", "en")

STAGE_WEIGHTS = {
    "prepare": 25,
    "metadata": 0,
    "scenes": 5,
    "speech": 15,
    "ocr": 15,
    "visual": 25,
    "audio_events": 10,
    "structure": 5,
}