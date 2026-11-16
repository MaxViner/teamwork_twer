from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class AnalyzeOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speech: bool = True
    ocr: bool = True
    metadata: bool = False

    language: str | None = Field(default=None, max_length=16)
    max_frames: int = Field(default=12, ge=1, le=50)
    whisper_model: Literal["tiny", "base", "small", "medium"] = "small"

    visual: bool = False
    audio_events: bool = False
    structure: bool = True
    visual_frames: int = Field(default=5, ge=1, le=50)

class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: uuid4().hex)
    source: Literal[
        "technical",
        "metadata",
        "scene",
        "speech",
        "ocr",
        "visual",
        "relation",
        "audio_event",
        "sequence",
        "reappearance",
    ]
    start: float = Field(default=0, ge=0, allow_inf_nan=False)
    end: float = Field(default=0, ge=0, allow_inf_nan=False)
    text: str
    corrected_text: str | None = None
    review: Literal["unreviewed", "accepted", "rejected"] = "unreviewed"
    artifact: str | None = None
    frame_artifact: str | None = None
    bbox: list[float] | None = None
    recognition_score: float | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False
    )
    extractor: str
    data: dict[str, Any] = Field(default_factory=dict)


class ReviewPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=20000)
    review: Literal["unreviewed", "accepted", "rejected"]


    # Тяжёлые модели запускаются только по явному выбору.
    visual: bool = False
    audio_events: bool = False

    # Структурный анализ не требует отдельной нейросети.
    structure: bool = True

    visual_frames: int = Field(
        default=6,
        ge=1,
        le=40,
    )