"""Метаданные файла и GPS.

Читает теги MP4/MOV/3GP (модель камеры, дата, координаты, XMP)
встроенным парсером, а при наличии ExifTool добавляет его данные.
Координаты и важные теги превращаются в наблюдения и metadata.json.
"""

import json
import shutil
from pathlib import Path

from app.services.mediaService.containers import (
    parse_gps,
    read_container_metadata,
)
from app.utils.observations import observation
from app.utils.commands import command
from app.utils.paths import relative


METADATA_KEYWORDS = (
    "gps",
    "latitude",
    "longitude",
    "altitude",
    "location",
    "datetime",
    "createdate",
    "creationdate",
    "date",
    "make",
    "model",
    "software",
    "device",
    "title",
    "encoder",
    "comment",
    "timezone",
)


def extract_metadata(folder: Path, run_folder: Path) -> dict:
    source = folder / "original.bin"

    tags = read_container_metadata(source)
    tags.update(_read_with_exiftool(source))

    selected = _select_tags(tags)
    coordinates = parse_gps(tags)

    if coordinates:
        selected["GPSPosition"] = (
            f"{coordinates[0][0]:.6f}, "
            f"{coordinates[0][1]:.6f}"
        )

    path = _save_metadata(run_folder, selected)

    observations = _build_observations(
        folder=folder,
        artifact=path,
        tags=selected,
        coordinates=coordinates,
    )

    note = (
        "Теги контейнера и устройства; подлинность не проверена. "
        "Один тег не подтверждает место съёмки."
    )

    if not selected:
        note = (
            "Метаданные в контейнере не найдены. "
            "Установите ExifTool для расширенного чтения тегов."
        )

    return {
        "tags": selected,
        "device": _device_name(selected),
        "created_at": _created_at(selected),
        "gps": [
            {
                "latitude": latitude,
                "longitude": longitude,
            }
            for latitude, longitude in coordinates
        ],
        "observations": observations,
        "note": note,
    }


def _read_with_exiftool(source: Path) -> dict:
    """Необязательное расширение через ExifTool."""

    if not shutil.which("exiftool"):
        return {}

    try:
        raw = command([
            "exiftool",
            "-json",
            "-n",
            "-ee",
            str(source),
        ])

        records = json.loads(raw)

    except Exception:
        return {}

    if not isinstance(records, list) or not records:
        return {}

    record = records[0]

    return {
        str(key): value
        for key, value in record.items()
        if any(
            keyword in str(key).lower()
            for keyword in METADATA_KEYWORDS
        )
    }


def _select_tags(tags: dict) -> dict:
    selected = {}

    for key, value in tags.items():
        if value in (None, "", [], {}):
            continue

        if not any(
            keyword in str(key).lower()
            for keyword in METADATA_KEYWORDS
        ):
            continue

        selected[str(key)] = value

    return dict(sorted(selected.items()))


def _save_metadata(
    run_folder: Path,
    records: dict,
) -> Path:
    path = run_folder / "metadata.json"
    path.write_text(
        json.dumps(
            records,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return path


def _build_observations(
    folder: Path,
    artifact: Path,
    tags: dict,
    coordinates: list[tuple[float, float]],
) -> list[dict]:
    artifact_path = relative(folder, artifact)
    observations = []

    for key, value in tags.items():
        observations.append(
            observation(
                source="metadata",
                text=f"{key}: {value}",
                artifact=artifact_path,
                extractor="mp4-container",
                data={
                    "tag": key,
                    "value": value,
                    "verified": False,
                },
            )
        )

    for latitude, longitude in coordinates:
        observations.append(
            observation(
                source="metadata",
                text=(
                    "GPS-координаты файла: "
                    f"{latitude:.6f}, {longitude:.6f}"
                ),
                artifact=artifact_path,
                extractor="mp4-container",
                data={
                    "kind": "gps_coordinates",
                    "tag": "GPSPosition",
                    "latitude": latitude,
                    "longitude": longitude,
                    "origin": "video_metadata",
                    "verified": False,
                },
            )
        )

    return observations


def _device_name(tags: dict) -> str | None:
    make = str(tags.get("Make", "")).strip()
    model = str(tags.get("Model", "")).strip()

    value = " ".join(
        part for part in (make, model) if part
    ).strip()

    return value or None


def _created_at(tags: dict) -> str | None:
    for key in (
        "CreateDate",
        "CreationDate",
        "DateTimeOriginal",
        "MediaCreateDate",
        "TrackCreateDate",
    ):
        value = tags.get(key)

        if value:
            return str(value)

    return None
