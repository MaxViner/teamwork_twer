from __future__ import annotations

from app.APIGateway.pipeline import STAGES
from app.config import STAGE_WEIGHTS


TARGET_STAGES = (
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
)


TARGET_WEIGHTS = {
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


def test_stages_match_target_order():
    assert STAGES == TARGET_STAGES


def test_stage_weights_match_stages():
    assert tuple(STAGE_WEIGHTS) == STAGES
    assert set(STAGE_WEIGHTS) == set(STAGES)


def test_stage_weights_values():
    assert STAGE_WEIGHTS == TARGET_WEIGHTS


def test_stage_weights_sum_to_hundred():
    total = sum(STAGE_WEIGHTS.values())

    assert abs(total - 100.0) < 1e-9, total


def test_all_weights_positive():
    assert all(value > 0 for value in STAGE_WEIGHTS.values())
