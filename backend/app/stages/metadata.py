import json
from pathlib import Path

from app.observations import observation
from app.utils.commands import command, require_tools
from app.utils.paths import relative


METADATA_KEYWORDS = (
    "gps",
    "latitude",
    "longitude",
    "altitude",
    "datetime",
    "createdate",
    "creationdate",
    "make",
    "model",
)


def extract_metadata(folder: Path, run_folder: Path) -> dict:
    require_tools("exiftool")

    records = _read_metadata(folder / "original.bin")
    selected = [_select_tags(record) for record in records]
    path = _save_metadata(run_folder, selected)

    return {
        "observations": _build_observations(folder, path, selected),
        "note": (
            "Теги исходного файла; подлинность не проверена. "
            "Один тег не подтверждает место съёмки."
        ),
    }


def _read_metadata(source: Path) -> list[dict]:
    raw = command([
        "exiftool",
        "-json",
        "-n",
        "-ee",
        str(source),
    ])

    return json.loads(raw)


def _select_tags(record: dict) -> dict:
    return {
        key: value
        for key, value in record.items()
        if any(keyword in key.lower() for keyword in METADATA_KEYWORDS)
    }


def _save_metadata(run_folder: Path, records: list[dict]) -> Path:
    path = run_folder / "metadata.json"
    path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def _build_observations(
    folder: Path,
    artifact: Path,
    records: list[dict],
) -> list[dict]:
    observations = []

    for record in records:
        for key, value in record.items():
            observations.append(
                observation(
                    source="metadata",
                    text=f"{key}: {value}",
                    artifact=relative(folder, artifact),
                    extractor="ExifTool",
                    data={
                        "tag": key,
                        "value": value,
                        "verified": False,
                    },
                )
            )

    return observations
