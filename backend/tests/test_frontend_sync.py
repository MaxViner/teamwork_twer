from __future__ import annotations

import re
from pathlib import Path

from app.APIGateway.pipeline import STAGES


FRONTEND = Path(__file__).resolve().parent.parent.parent / "frontend" / "src"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _string_list(source: str, name: str) -> list[str]:
    match = re.search(
        rf"{name}\s*=\s*\[(.*?)\]",
        source,
        re.S,
    )

    assert match, f"{name} not found"

    return re.findall(r"[\"']([^\"']+)[\"']", match.group(1))


def test_frontend_stage_order_matches_backend():
    source = _read(FRONTEND / "constants" / "labels.js")
    order = _string_list(source, "STAGE_ORDER")

    assert tuple(order) == STAGES


def test_frontend_stage_labels_cover_all_stages():
    source = _read(FRONTEND / "constants" / "labels.js")
    block = re.search(r"STAGE_LABELS\s*=\s*\{(.*?)\};", source, re.S)

    assert block, "STAGE_LABELS not found"

    keys = re.findall(r"^\s*([a-z_]+)\s*:", block.group(1), re.M)

    for stage in STAGES:
        assert stage in keys, stage


def test_upload_options_cover_all_stages():
    source = _read(FRONTEND / "constants" / "uploadOptions.js")
    block = re.search(
        r"DEFAULT_UPLOAD_OPTIONS\s*=\s*\{(.*?)\};",
        source,
        re.S,
    )

    assert block, "DEFAULT_UPLOAD_OPTIONS not found"

    keys = re.findall(r"^\s*([a-z_]+)\s*:", block.group(1), re.M)

    for stage in STAGES:
        if stage in {"prepare", "scenes"}:
            continue

        assert stage in keys, stage


def test_nav_ends_with_dossier_then_prompt():
    source = _read(FRONTEND / "constants" / "sectionsNav.js")
    ids = [
        value
        for value in _string_list(source, "ANALYSIS_SECTIONS")
        if value.startswith("section-")
    ]

    assert ids[-2:] == [
        "section-dossier",
        "section-location-prompt",
    ]


def test_sections_have_panels():
    source = _read(FRONTEND / "sections" / "AnalysisSections.jsx")

    for section in (
        "section-visual-analysis",
        "section-place-profile",
        "section-location-prompt",
    ):
        assert f'id="{section}"' in source, section
