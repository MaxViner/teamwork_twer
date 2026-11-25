"""Pydantic-модели данных.

AnalyzeOptions описывает настройки анализа из формы загрузки,
Observation — одно сохранённое наблюдение (текст, время, источник,
артефакты), ReviewPatch — пользовательскую правку наблюдения.
Модели проверяют типы и не дают сохранить лишние поля.
"""

from typing import Any, Literal
from uuid import uuid4


from pydantic import BaseModel, ConfigDict, Field



class AnalyzeOptions(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )



    metadata: bool = True
    speech: bool = True
    ocr: bool = True
    visual_analysis: bool = True
    place_profile: bool = True
    location_evidence: bool = True
    audio_structure: bool = True
    structure: bool = True
    summary: bool = True
    video_structure: bool = True
    location_prompt: bool = True

    # Старые имена оставлены для совместимости с существующими
    # клиентами и job.json; новые этапы читают их как fallback.
    scene_objects: bool = True
    faces: bool = True
    visual_profile: bool = True
    road_geometry: bool = True
    comprehension: bool = True
    landmarks: bool = True
    ai_prompt: bool = True



    language: str | None = Field(
        default=None,
        max_length=16,
    )


    max_frames: int = Field(
        default=500,
        ge=1,
        le=2000,
    )


    whisper_model: Literal[
        "tiny",
        "base",
        "small",
        "medium",
    ] = "small"



class Observation(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )



    id: str = Field(
        default_factory=lambda: uuid4().hex,
    )


    source: Literal[
        "technical",
        "metadata",
        "scene",
        "speech",
        "ocr",
        "audio_structure",
        "audio_event",
        "structure",
        "reappearance",
        "scene_objects",
        "faces",
        "visual_profile",
        "road_geometry",
        "location_evidence",
        "summary",
        "video_structure",
        "comprehension",
        "landmarks",
        "ai_prompt",
        "visual_analysis",
        "place_profile",
        "location_prompt",
        "odometry",
        "bev",
    ]


    start: float = Field(
        default=0,
        ge=0,
        allow_inf_nan=False,
    )


    end: float = Field(
        default=0,
        ge=0,
        allow_inf_nan=False,
    )


    text: str
    corrected_text: str | None = None


    review: Literal[
        "unreviewed",
        "accepted",
        "rejected",
    ] = "unreviewed"


    artifact: str | None = None
    frame_artifact: str | None = None
    bbox: list[float] | None = None


    recognition_score: float | None = Field(
        default=None,
        ge=0,
        le=1,
        allow_inf_nan=False,
    )


    extractor: str
    data: dict[str, Any] = Field(
        default_factory=dict,
    )



class ReviewPatch(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )



    text: str = Field(
        max_length=20000,
    )


    review: Literal[
        "unreviewed",
        "accepted",
        "rejected",
    ]