from __future__ import annotations

import numpy as np
import pytest

from app.services.weakCluesService import (
    aggregation,
    birdnet,
    infrastructure,
    phenology,
    service,
    stacking,
    visual,
)


def test_phenology_window_for_latitude_band():
    window = phenology.date_window(
        "leaf_out",
        latitude=55.4,
        reference="2026-05-01",
    )

    assert window["start"] == "2026-04-20"
    assert window["end"] == "2026-05-10"
    assert window["band"] == [55, 56]


def test_phenology_window_without_latitude_is_wider():
    narrow = phenology.date_window(
        "leaf_out",
        latitude=55.4,
        reference="2026-05-01",
    )
    wide = phenology.date_window(
        "leaf_out",
        reference="2026-05-01",
    )

    assert wide["band"] is None
    assert wide["start"] <= narrow["start"]
    assert wide["end"] >= narrow["end"]


def test_phenology_conflict_with_created_at():
    window = phenology.date_window(
        "summer",
        latitude=56.0,
        reference="2026-07-01",
    )

    assert phenology.conflict_with_created_at(
        window,
        "2026-07-01T12:00:00",
    ) is False
    assert phenology.conflict_with_created_at(
        window,
        "2026-01-15T12:00:00",
    ) is True


def test_phenology_frames_become_clue():
    frames = [
        {"timestamp": 1.0, "metrics": {"vegetation": 25, "snow": 0}},
        {"timestamp": 2.0, "metrics": {"vegetation": 30, "snow": 0}},
    ]

    result = phenology.analyze_frames(
        frames,
        created_at="2026-07-10",
        latitude=56.2,
    )
    clue = result["clue"]

    assert result["phase"] == "summer"
    assert clue["kind"] == "phenology"
    assert clue["details"]["leaf_pct"] == 82
    assert clue["details"]["latitude_band"] == [56, 57]
    assert clue["details"]["date_conflict"] is False


@pytest.mark.parametrize(
    ("text", "road_ref", "km"),
    [
        ("М-10 124 км", "М-10", 124.0),
        ("Р-132", "Р-132", None),
        ("12+500", None, 12.5),
        ("12 км", None, 12.0),
        ("км 12", None, 12.0),
        ("1Р-132 7,5 км", "1Р-132", 7.5),
        ("просто текст", None, None),
    ],
)
def test_parse_km_post(text, road_ref, km):
    parsed = infrastructure.parse_km_post(text)

    if road_ref is None and km is None:
        assert parsed is None
        return

    assert parsed["road_ref"] == road_ref
    assert parsed["km"] == km


def test_road_candidates_are_limited_and_ranked():
    evidence = [
        infrastructure.km_post_clue("М-10 124 км", confidence=0.8),
        infrastructure.km_post_clue("М-10 126 км", confidence=0.7),
        infrastructure.road_noise_clue(
            {"loud_ratio": 0.5, "mean_rms": 0.06},
            duration=60,
        ),
        infrastructure.km_post_clue("Р-132 10 км", confidence=0.5),
    ]

    candidates = infrastructure.road_candidates(evidence, limit=5)

    assert 1 <= len(candidates) <= 5
    assert candidates[0]["road_ref"] == "М-10"
    assert candidates[0]["km_range"] == [124.0, 126.0]


def test_road_noise_classes():
    assert infrastructure.classify_road_noise(
        {"loud_ratio": 0.5, "mean_rms": 0.06},
    ) == "трасса"
    assert infrastructure.classify_road_noise(
        {"loud_ratio": 0.2, "mean_rms": 0.03},
    ) == "местная дорога"
    assert infrastructure.classify_road_noise(
        {"loud_ratio": 0.0, "mean_rms": 0.0},
    ) is None


def test_aggregation_counts_orthogonal_channels():
    evidence = [
        phenology.build_clue("summer", leaf_pct=80),
        birdnet.species_clues([{
            "scientific": "Crex crex",
            "confidence": 0.8,
            "windows": 2,
        }], duration=60)[0],
        infrastructure.km_post_clue("М-10 124 км", confidence=0.8),
    ]

    result = aggregation.aggregate(evidence, duration=60)

    assert result["orthogonal_channels"] == 3
    assert result["road_candidate_count"] == 1
    assert 0 < result["combined_confidence"] < 1


def test_correlated_channels_do_not_inflate_score():
    correlated = [
        {
            "kind": "visual_profile",
            "text": f"ландшафт {index}",
            "confidence": 0.6,
        }
        for index in range(5)
    ]

    result = aggregation.aggregate(correlated)

    assert result["orthogonal_channels"] == 1


def test_phenology_is_not_transferred_between_clusters():
    evidence = [
        phenology.build_clue("summer", leaf_pct=80),
        infrastructure.km_post_clue(
            "М-10 124 км",
            confidence=0.8,
            timestamp=10,
        ),
        infrastructure.km_post_clue(
            "М-10 130 км",
            confidence=0.8,
            timestamp=40,
        ),
    ]

    clusters = aggregation.cluster_evidence(
        evidence,
        duration=60,
        window=12,
    )

    assert len(clusters) == 2

    for cluster in clusters:
        assert "phenology" not in cluster["kinds"]
        assert cluster["phenology_transfer_blocked"] is True
        assert cluster["global_items"] == 1


def test_stack_images_aligns_shifted_frames():
    rng = np.random.default_rng(7)
    base = rng.integers(0, 255, size=(90, 160), dtype=np.uint8)

    frames = []

    for shift in range(5):
        moved = np.float32([[1, 0, shift], [0, 1, shift]])
        warped = stacking.cv2.warpAffine(
            base,
            moved,
            (160, 90),
            borderMode=stacking.cv2.BORDER_REPLICATE,
        )
        noise = rng.normal(0, 12, warped.shape)
        frames.append(np.clip(warped + noise, 0, 255).astype(np.uint8))

    result = stacking.stack_images(frames)

    assert result["image"] is not None
    assert result["used"] >= 4
    assert result["sharpness"] > 0

    assert stacking.stack_images(frames[:2])["image"] is None


def test_stack_crops_uses_boxes():
    rng = np.random.default_rng(3)
    base = rng.integers(0, 255, size=(120, 200), dtype=np.uint8)

    import tempfile
    from pathlib import Path

    paths = []

    with tempfile.TemporaryDirectory() as folder:
        for index in range(4):
            path = Path(folder) / f"{index}.png"
            stacking.cv2.imwrite(str(path), base)
            paths.append(path)

        result = stacking.stack_crops(
            paths,
            [[40, 20, 120, 90]] * 4,
            margin=0.1,
        )

    assert result["image"] is not None
    assert result["size"] == [96, 84]


def test_birdnet_without_model_degrades(monkeypatch, tmp_path):
    monkeypatch.setattr(birdnet, "MODEL_PATH", tmp_path / "no.onnx")
    monkeypatch.setattr(
        birdnet,
        "LABELS_PATH",
        tmp_path / "no.txt",
    )

    assert birdnet.model_available() is False

    result = birdnet.analyze_waveform(np.zeros(48000, dtype=np.float32))

    assert result["detections"] == []
    assert "BirdNET" in result["note"]


def test_birdnet_species_clue_has_month_window():
    clues = birdnet.species_clues([{
        "scientific": "Oriolus oriolus",
        "confidence": 0.7,
        "windows": 3,
    }], duration=45)

    assert len(clues) == 1
    assert clues[0]["kind"] == "bird_species"
    assert clues[0]["details"]["months"] == [5, 7]
    assert clues[0]["country_hints"]["RU"] > 0
    assert clues[0]["details"]["narrow_range"] is True


def test_collect_weak_clues_and_readiness():
    stages = {
        "metadata": {
            "result": {"created_at": "2026-07-10T12:00:00"},
        },
        "visual_analysis": {
            "result": {
                "frames": [
                    {
                        "timestamp": 1.0,
                        "metrics": {"vegetation": 28, "snow": 0},
                    },
                ],
                "stacked_readings": [
                    {
                        "text": "М-10 124 км",
                        "confidence": 0.8,
                        "timestamp": 10.0,
                    },
                ],
            },
        },
        "audio_structure": {
            "result": {
                "profile": {
                    "loud_ratio": 0.4,
                    "mean_rms": 0.06,
                    "mean_centroid_hz": 900,
                },
                "bird_species": [{
                    "scientific": "Crex crex",
                    "confidence": 0.8,
                    "windows": 2,
                }],
            },
        },
    }

    clues = service.collect_weak_clues(stages, duration=60)
    kinds = {item["kind"] for item in clues}

    assert {"phenology", "bird_species", "km_post", "road_noise"} <= kinds

    result = service.aggregate(clues, duration=60)

    assert result["orthogonal_channels"] >= 3
    assert 0 < result["road_candidate_count"] <= 5
    assert service.readiness(result)["ready"] is True
