"""Сборка Markdown-отчёта.

Отчёт читает сохранённые результаты этапов и складывает их в
разделы: сведения о задании, локационное досье, метаданные и GPS,
состояние анализаторов, речь, надписи, уникальные объекты, сводку
по ключевым кадрам и ограничения интерпретации. Ничего заново
не анализируется.
"""

import json
import math
import re
import unicodedata

from collections import Counter
from datetime import datetime, timezone

from app.stages.scene_objects import (
    CATEGORY_LABELS_RU,
    CATEGORY_ORDER,
    unique_objects_from_frames,
)


# ============================================================
# Названия этапов и типов наблюдений
# ============================================================

STAGE_NAMES = {
    "prepare": "Подготовка видео",
    "metadata": "Метаданные",
    "scenes": "Разделение на сцены",
    "speech": "Распознавание речи",
    "audio_structure": "Звуковая структура",
    "ocr": "Распознавание надписей",
    "scene_objects": "Объекты и признаки места",
    "visual_profile": "Визуальный профиль места",
    "road_geometry": "Геометрия дороги",
    "location_evidence": "Географические улики",
    "visual": "Визуальные признаки",
    "audio_events": "Звуковые события",
    "structure": "Структура и повторения",
}

SOURCE_NAMES = {
    "technical": "Технические сведения",
    "metadata": "Метаданные",
    "scene": "Сцена",
    "speech": "Речь",
    "ocr": "Надпись",
    "audio_structure": "Звуковая структура",
    "audio_event": "Звуковое событие",
    "visual": "Визуальное наблюдение",
    "visual_profile": "Визуальный профиль",
    "relation": "Пространственное отношение",
    "sequence": "Последовательность",
    "reappearance": "Повторное появление",
    "scene_objects": "Объекты сцены",
    "road_geometry": "Геометрия дороги",
    "location_evidence": "Географическая улика",
}

STATUS_NAMES = {
    "created": "Создано",
    "pending": "Ожидание",
    "queued": "В очереди",
    "running": "Выполняется",
    "completed": "Завершено",
    "partial": "Частичный результат",
    "failed": "Ошибка",
    "skipped": "Пропущено",
}

REVIEW_NAMES = {
    "unreviewed": "Не проверено",
    "accepted": "Подтверждено пользователем",
    "rejected": "Отклонено пользователем",
}

CATEGORY_NAMES = {
    "building": "Здания",
    "infrastructure": "Инфраструктура",
    "transport": "Транспорт",
    "sign": "Знаки и указатели",
    "terrain": "Рельеф",
    "vegetation": "Растительность",
    "water": "Водные объекты",
    "other": "Другие объекты",
}

KNOWN_SOURCES = set(SOURCE_NAMES)

KEY_FRAME_SPEECH_WINDOW_SECONDS = 10
KEY_FRAME_SPEECH_LIMIT = 5
KEY_FRAME_LIMIT = 60
KEY_FRAME_MATCH_TOLERANCE_SECONDS = 0.75
ROAD_MATCH_TOLERANCE_SECONDS = 0.2


# ============================================================
# Вспомогательные функции
# ============================================================

def mapping(value):
    """Возвращает словарь или пустой словарь."""
    return value if isinstance(value, dict) else {}


def records(value):
    """Возвращает только словари из списка."""
    if not isinstance(value, list):
        return []

    return [
        item
        for item in value
        if isinstance(item, dict)
    ]


def block(value, language="text"):
    """
    Помещает текст в блок Markdown.

    Длина ограждения выбирается так, чтобы обратные кавычки
    внутри извлечённого текста не закрывали блок.
    """
    text = str(value)

    longest = max(
        (
            len(match.group())
            for match in re.finditer(r"`+", text)
        ),
        default=0,
    )

    fence = "`" * max(3, longest + 1)

    return f"{fence}{language}\n{text}\n{fence}"


def json_block(value):
    return block(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        language="json",
    )


def numeric_time(value):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None

    if not math.isfinite(number) or number < 0:
        return None

    return number


def timestamp(value):
    seconds = numeric_time(value)

    if seconds is None:
        return "не задано"

    milliseconds = round(seconds * 1000)

    hours, remainder = divmod(
        milliseconds,
        3_600_000,
    )
    minutes, remainder = divmod(
        remainder,
        60_000,
    )
    seconds, milliseconds = divmod(
        remainder,
        1000,
    )

    return (
        f"{hours:02d}:{minutes:02d}:"
        f"{seconds:02d}.{milliseconds:03d}"
    )


def interval(item):
    if item.get("source") == "technical":
        return "весь файл"

    start = item.get("start")
    end = item.get("end")

    if start == end:
        return timestamp(start)

    return f"{timestamp(start)} — {timestamp(end)}"


def sort_key(item):
    value = numeric_time(item.get("start"))

    return (
        value is None,
        value if value is not None else 0,
        str(item.get("id", "")),
    )


def effective_text(item):
    """
    Использует исправление, если оно существует.

    Пустая строка тоже считается сохранённым исправлением.
    """
    corrected = item.get("corrected_text")

    if corrected is not None:
        return str(corrected)

    return str(item.get("text", ""))


def normalized_text(value):
    text = unicodedata.normalize(
        "NFKC",
        str(value),
    )

    return " ".join(text.casefold().split())


def is_previous_result(stage):
    result_run_id = stage.get("result_run_id")
    run_id = stage.get("run_id")

    return bool(
        result_run_id
        and run_id
        and result_run_id != run_id
    )


def collect_observations(job):
    """
    Собирает текущие доступные наблюдения.

    История попыток повторно не добавляется, чтобы не
    дублировать результаты. Метаданные и GPS включаются:
    это самые сильные признаки места съёмки.
    """
    observations = []

    for stage_name, raw_stage in mapping(
        job.get("stages")
    ).items():
        stage = mapping(raw_stage)

        for original in records(stage.get("observations")):
            item = dict(original)

            item["_provenance"] = {
                "stage": stage_name,
                "stage_status": stage.get("status"),
                "run_id": stage.get("run_id"),
                "result_run_id": stage.get("result_run_id"),
                "previous_result": is_previous_result(stage),
            }

            observations.append(item)

    return sorted(observations, key=sort_key)


def select_items(observations, sources):
    return [
        item
        for item in observations
        if item.get("source") in sources
    ]


def append_observation(lines, item, number):
    source = item.get("source", "unknown")
    source_name = SOURCE_NAMES.get(source, "Другой источник")

    lines.extend([
        f"### {number}. {source_name} · {interval(item)}",
        "",
        "Оригинальный результат:",
        block(item.get("text", "")),
        "",
    ])

    if item.get("corrected_text") is not None:
        lines.extend([
            "Исправление пользователя:",
            block(item["corrected_text"]),
            "",
        ])

    review = item.get("review", "unreviewed")

    lines.extend([
        "Статус проверки:",
        block(REVIEW_NAMES.get(review, review)),
        "",
    ])

    provenance = mapping(item.get("_provenance"))

    if provenance.get("previous_result"):
        lines.extend([
            "**Внимание:** показан сохранённый результат "
            "предыдущей попытки этого этапа.",
            "",
        ])

    if item.get("recognition_score") is not None:
        lines.extend([
            "Оценка распознавания:",
            block(item["recognition_score"]),
            "",
            "Эта оценка не является вероятностью геолокации.",
            "",
        ])

    lines.extend([
        "Происхождение и артефакты:",
        json_block({
            "observation_id": item.get("id"),
            "source": source,
            "extractor": item.get("extractor"),
            **provenance,
            "artifact": item.get("artifact"),
            "frame_artifact": item.get("frame_artifact"),
            "bbox_normalized": item.get("bbox"),
            "reviewed_at": item.get("reviewed_at"),
        }),
        "",
    ])

    data = mapping(item.get("data"))
    segments = records(data.get("segments"))

    if segments and source != "speech":
        lines.extend([
            "Фрагменты:",
            "",
        ])

        for segment in segments[:120]:
            text = str(
                segment.get("text", "")
            ).strip()

            if not text:
                continue

            lines.append(
                f"- `{timestamp(segment.get('start'))}`"
                f" — {text}"
            )

        if len(segments) > 120:
            lines.append(
                f"Показаны первые 120 из "
                f"{len(segments)} фрагментов."
            )

        lines.append("")

    if segments:
        data = {
            key: value
            for key, value in data.items()
            if key != "segments"
        }

    if data:
        lines.extend([
            "Дополнительные данные анализатора:",
            json_block(data),
            "",
        ])

    # Не теряем дополнительные поля новых анализаторов.
    handled = {
        "id",
        "source",
        "start",
        "end",
        "text",
        "corrected_text",
        "review",
        "recognition_score",
        "extractor",
        "artifact",
        "frame_artifact",
        "bbox",
        "reviewed_at",
        "data",
        "_provenance",
    }

    extra = {
        key: value
        for key, value in item.items()
        if key not in handled
    }

    if extra:
        lines.extend([
            "Другие сохранённые поля:",
            json_block(extra),
            "",
        ])


def append_section(lines, title, items):
    lines.extend([
        f"## {title}",
        "",
    ])

    if not items:
        lines.extend([
            "Сохранённых наблюдений нет. Причина может быть "
            "в отключённом, пропущенном или завершившемся "
            "ошибкой этапе. Смотрите состояние анализаторов.",
            "",
        ])

        return

    for number, item in enumerate(items, start=1):
        append_observation(lines, item, number)


def stage_result(stages, name):
    return mapping(
        mapping(stages.get(name)).get("result")
    )


def stage_frames(stages, name):
    """Возвращает только словари кадров из результата этапа."""
    return records(
        stage_result(stages, name).get("frames")
    )


def key_frame_items(stages):
    """
    Собирает ключевые кадры из всех визуальных этапов.

    Один и тот же таймкод может встречаться в объектах, визуальном
    профиле и OCR. Все сведения объединяются в одну запись, чтобы
    отчёт не повторял кадр несколько раз.
    """
    collected = {}

    for stage_name in (
        "visual_profile",
        "scene_objects",
        "ocr",
    ):
        for frame in stage_frames(stages, stage_name):
            moment = numeric_time(frame.get("timestamp"))

            if moment is None:
                continue

            key = round(moment, 3)
            item = collected.setdefault(key, {
                "timestamp": moment,
                "artifact": None,
                "objects": [],
                "descriptors": {},
                "metrics": {},
            })

            if not item["artifact"]:
                item["artifact"] = frame.get("artifact")

            objects = records(frame.get("objects"))

            if objects:
                item["objects"] = objects

            descriptors = mapping(frame.get("descriptors"))

            if descriptors:
                item["descriptors"] = descriptors

            metrics = mapping(frame.get("metrics"))

            if metrics:
                item["metrics"] = metrics

    return [
        collected[key]
        for key in sorted(collected)
    ]


def semantic_road_frames(stages):
    """
    Возвращает долю дороги по семантической маске для каждого кадра.

    Для старых заданий это позволяет отбросить ложные срабатывания
    геометрии дороги без повторного запуска этапа. Если маска
    недоступна, возвращается None и решение не переопределяется.
    """
    result = stage_result(stages, "scene_objects")
    method = result.get("method")

    if method and method != "segformer":
        return None

    frames = records(result.get("frames"))

    if not frames:
        return None

    evidence = {}

    for frame in frames:
        moment = numeric_time(frame.get("timestamp"))

        if moment is None:
            continue

        percent = 0.0

        for item in records(frame.get("objects")):
            if item.get("label") in {
                "road",
                "path",
                "bridge",
            }:
                percent += float(
                    item.get("area_percent") or 0
                )

        evidence[round(moment, 3)] = percent

    return evidence or None


def road_allowed_by_mask(evidence, moment):
    """Проверяет кадр по семантической маске дороги."""
    if not evidence or moment is None:
        return True

    nearest_key = None
    nearest_diff = None

    for key in evidence:
        diff = abs(key - moment)

        if nearest_diff is None or diff < nearest_diff:
            nearest_key = key
            nearest_diff = diff

    if nearest_key is None or nearest_diff is None:
        return False

    if nearest_diff > ROAD_MATCH_TOLERANCE_SECONDS:
        return False

    return evidence[nearest_key] >= 1.0


def road_evidence(stages, observations):
    """Собирает кадры с дорогой, отбрасывая ложные срабатывания."""
    segments = []

    for item in observations:
        if item.get("source") != "road_geometry":
            continue

        data = mapping(item.get("data"))
        stored = records(data.get("segments"))

        if stored:
            for segment in stored:
                segments.append({
                    **segment,
                    "confidence": (
                        segment.get("confidence")
                        if segment.get("confidence") is not None
                        else data.get("confidence")
                    ),
                })

            continue

        segments.append({
            "start": item.get("start"),
            "end": item.get("end"),
            "text": effective_text(item),
            "confidence": data.get("confidence"),
            "semantic_road_percent": data.get(
                "semantic_road_percent"
            ),
        })

    evidence = semantic_road_frames(stages)

    return [
        segment
        for segment in segments
        if road_allowed_by_mask(
            evidence,
            numeric_time(segment.get("start")),
        )
    ]


def speech_evidence(observations):
    """Собирает реплики речи из новых и старых наблюдений."""
    segments = []

    for item in observations:
        if item.get("source") != "speech":
            continue

        stored = records(
            mapping(item.get("data")).get("segments")
        )

        if stored:
            for segment in stored:
                start = numeric_time(segment.get("start"))

                if start is None:
                    continue

                end = numeric_time(segment.get("end"))

                segments.append({
                    "start": start,
                    "end": end if end is not None else start,
                    "text": str(segment.get("text", "")).strip(),
                })

            continue

        start = numeric_time(item.get("start"))

        if start is None:
            continue

        end = numeric_time(item.get("end"))

        segments.append({
            "start": start,
            "end": end if end is not None else start,
            "text": effective_text(item).strip(),
        })

    return sorted(segments, key=lambda item: item["start"])


def speech_distance(segment, moment):
    """Расстояние от таймкода до реплики; внутри реплики — ноль."""
    if moment < segment["start"]:
        return segment["start"] - moment

    if moment > segment["end"]:
        return moment - segment["end"]

    return 0.0


def closest_speech(segments, moment):
    """Ближайшие реплики, затем снова по времени."""
    chosen = sorted(
        segments,
        key=lambda item: speech_distance(item, moment),
    )[:KEY_FRAME_SPEECH_LIMIT]

    return sorted(
        chosen,
        key=lambda item: item["start"],
    )


def ocr_evidence(observations):
    """Собирает надписи с привязкой к кадру."""
    items = []

    for item in observations:
        if item.get("source") != "ocr":
            continue

        text = effective_text(item).strip()

        if not text:
            continue

        items.append({
            "start": numeric_time(item.get("start")),
            "frame_artifact": item.get("frame_artifact"),
            "text": text,
        })

    return items


def nearest_evidence(segments, moment):
    """Ближайший фрагмент в пределах допуска или None."""
    nearest = None
    nearest_diff = None

    for segment in segments:
        start = numeric_time(segment.get("start"))

        if start is None:
            continue

        diff = abs(start - moment)

        if nearest_diff is None or diff < nearest_diff:
            nearest = segment
            nearest_diff = diff

    if nearest_diff is None:
        return None

    if nearest_diff > KEY_FRAME_MATCH_TOLERANCE_SECONDS:
        return None

    return nearest


def scene_bounds(stages, moment):
    """Возвращает номер сцены и её границы для таймкода."""
    intervals = stage_result(stages, "scenes").get(
        "intervals"
    )

    if not isinstance(intervals, list) or not intervals:
        return None

    index = None

    for position, interval_value in enumerate(intervals):
        if not isinstance(
            interval_value,
            (list, tuple),
        ) or len(interval_value) < 2:
            continue

        start = numeric_time(interval_value[0])
        end = numeric_time(interval_value[1])

        if start is None or end is None:
            continue

        if start <= moment < end:
            index = position
            break

    if index is None:
        index = len(intervals) - 1

    interval_value = intervals[index]

    return (
        index + 1,
        numeric_time(interval_value[0]),
        numeric_time(interval_value[1]),
    )


def metric_text(metrics):
    """Короткая строка числовых метрик визуального профиля."""
    parts = []

    if numeric_time(metrics.get("brightness")) is not None:
        parts.append(
            f"яркость {round(float(metrics['brightness']))}"
        )

    if numeric_time(metrics.get("contrast")) is not None:
        parts.append(
            f"контраст {round(float(metrics['contrast']))}"
        )

    if numeric_time(metrics.get("saturation")) is not None:
        parts.append(
            f"насыщенность "
            f"{round(float(metrics['saturation']))}"
        )

    return ", ".join(parts)


def key_frames_section(stages, observations):
    """
    Сводный раздел по ключевым кадрам.

    Для каждого кадра объединяются объекты, визуальный профиль,
    дорога, распознанный текст и речь в пределах ±10 секунд.
    """
    frames = key_frame_items(stages)

    lines = [
        "## 17. Ключевые кадры",
        "",
        "Один сводный вывод на исследованный кадр: объекты, "
        "визуальный профиль, геометрия дороги, текст на кадре "
        "и речь в пределах "
        f"±{KEY_FRAME_SPEECH_WINDOW_SECONDS} секунд. "
        "Таймкоды приблизительные.",
        "",
    ]

    if not frames:
        lines.extend([
            "Ключевые кадры не найдены: визуальные этапы "
            "не завершены или не сохранили кадры.",
            "",
        ])
        return lines

    roads = road_evidence(stages, observations)
    speech = speech_evidence(observations)
    ocr = ocr_evidence(observations)

    for number, frame in enumerate(
        frames[:KEY_FRAME_LIMIT],
        start=1,
    ):
        moment = frame["timestamp"]
        scene = scene_bounds(stages, moment)

        title = f"### Кадр {number} · {timestamp(moment)}"

        if scene:
            title += (
                f" · сцена {scene[0]} "
                f"({timestamp(scene[1])} — "
                f"{timestamp(scene[2])})"
            )

        lines.extend([title, ""])

        objects = sorted(
            frame["objects"],
            key=lambda item: -float(
                item.get("area_percent") or 0
            ),
        )

        if objects:
            lines.append(
                "- Объекты: "
                + ", ".join(
                    f"{item.get('label_ru') or item.get('label')}"
                    f" ({item.get('area_percent', 0)}%)"
                    for item in objects[:6]
                )
                + "."
            )
        else:
            lines.append("- Объекты: не найдены.")

        descriptors = frame["descriptors"]
        metrics = frame["metrics"]

        place_parts = [
            descriptors.get("lighting"),
            descriptors.get("weather"),
            descriptors.get("season"),
        ]

        place = "; ".join(
            str(part)
            for part in place_parts
            if part
        )

        landscape = descriptors.get("landscape")

        place_line = f"- Место: {place}." if place else "- Место: не определено."

        if isinstance(landscape, list) and landscape:
            place_line += (
                " Ландшафт: "
                + ", ".join(str(item) for item in landscape)
                + "."
            )

        lines.append(place_line)

        numbers = metric_text(metrics)

        if numbers:
            lines.append(f"- Метрики кадра: {numbers}.")

        road = nearest_evidence(roads, moment)

        if road:
            road_text = re.sub(
                r"^Дорога:\s*",
                "",
                str(road.get("text", "")).strip(),
                flags=re.IGNORECASE,
            )

            extra = []

            if road.get("semantic_road_percent") is not None:
                extra.append(
                    "маска дороги "
                    f"{road['semantic_road_percent']}%"
                )

            if road.get("confidence") is not None:
                extra.append(
                    "уверенность "
                    f"{round(float(road['confidence']) * 100)}%"
                )

            suffix = (
                f" ({', '.join(extra)})"
                if extra
                else ""
            )

            lines.append(
                f"- Дорога: {road_text}{suffix}."
            )
        else:
            lines.append("- Дорога: признаков не найдено.")

        frame_texts = []

        for item in ocr:
            start = item["start"]

            matches = (
                item["frame_artifact"]
                and item["frame_artifact"]
                == frame["artifact"]
            )

            if not matches and start is not None:
                matches = (
                    abs(start - moment)
                    <= KEY_FRAME_MATCH_TOLERANCE_SECONDS
                )

            if matches and item["text"] not in frame_texts:
                frame_texts.append(item["text"])

        if frame_texts:
            lines.append(
                "- Текст на кадре: "
                + "; ".join(
                    f"«{text}»"
                    for text in frame_texts[:3]
                )
                + "."
            )

        nearby = [
            item
            for item in speech
            if (
                item["end"] >= (
                    moment - KEY_FRAME_SPEECH_WINDOW_SECONDS
                )
                and item["start"] <= (
                    moment + KEY_FRAME_SPEECH_WINDOW_SECONDS
                )
            )
        ]

        if nearby:
            shown = closest_speech(nearby, moment)

            lines.append("- Речь рядом:")

            for item in shown:
                lines.append(
                    f"  - `{timestamp(item['start'])}` — "
                    f"{item['text']}"
                )

            if len(nearby) > len(shown):
                lines.append(
                    f"  - Показаны {len(shown)} ближайших "
                    f"из {len(nearby)} реплик."
                )
        else:
            lines.append(
                "- Речь рядом: реплик в окрестности нет."
            )

        lines.append("")

    if len(frames) > KEY_FRAME_LIMIT:
        lines.extend([
            f"Показаны первые {KEY_FRAME_LIMIT} из "
            f"{len(frames)} ключевых кадров.",
            "",
        ])

    return lines


def location_dossier_section(stages):
    """Локационное досье: координаты, страны, места, запросы."""
    result = stage_result(stages, "location_evidence")
    dossier = mapping(result.get("dossier"))

    lines = [
        "## 4. Локационное досье",
        "",
        "Досье объединяет независимые признаки места и "
        "ранжирует страны и места-кандидаты. Это гипотезы "
        "для проверки, а не подтверждённый адрес. Каждый "
        "вывод можно проследить до исходного наблюдения.",
        "",
    ]

    if not dossier:
        lines.extend([
            "Досье не сформировано: этап «Географические "
            "улики» не завершён или не нашёл признаков.",
            "",
        ])
        return lines

    lines.extend([
        "Краткий итог:",
        block(dossier.get("summary", "")),
        "",
    ])

    coordinates = records(dossier.get("coordinates"))

    if coordinates:
        lines.extend(["GPS-координаты:", ""])

        for item in coordinates:
            lines.append(
                f"- {item.get('latitude')}, "
                f"{item.get('longitude')} "
                f"(источник: {item.get('origin') or 'не указан'})"
            )

        lines.append("")
    else:
        lines.extend([
            "GPS-координаты не найдены. Для видео без геотегов "
            "это ожидаемо, поэтому важны остальные признаки.",
            "",
        ])

    countries = records(dossier.get("country_candidates"))

    lines.extend(["Страны-кандидаты:", ""])

    if countries:
        for item in countries:
            signals = item.get("signals") or []

            lines.append(
                f"- {item.get('name') or item.get('code')} — "
                f"относительная оценка {item.get('score')}"
            )

            for signal in signals[:6]:
                lines.append(f"  - {signal}")
    else:
        lines.append(
            "- Недостаточно признаков для ранжирования стран."
        )

    lines.append("")

    places = records(dossier.get("place_candidates"))

    lines.extend(["Места и объекты-кандидаты:", ""])

    if places:
        for item in places:
            lines.append(
                f"- {item.get('text')} "
                f"(упоминаний: {item.get('count', 0)}, "
                f"оценка: {item.get('confidence')})"
            )
    else:
        lines.append(
            "- Точные места не выделены. Ищите по признакам "
            "ниже: язык, бренды, дорожная геометрия, ландшафт."
        )

    lines.append("")

    queries = dossier.get("search_queries")

    if isinstance(queries, list) and queries:
        lines.extend([
            "Поисковые запросы для проверки на карте и в "
            "поиске:",
            "",
        ])

        for query in queries:
            lines.append(f"- {query}")

        lines.append("")

    profile = mapping(dossier.get("profile"))

    if profile:
        lines.extend([
            "Сводный профиль признаков:",
            json_block(profile),
            "",
        ])

    counts = mapping(dossier.get("evidence_counts"))

    if counts:
        lines.extend([
            "Количество признаков по типам:",
            json_block(counts),
            "",
        ])

    limitations = dossier.get("limitations")

    if limitations:
        lines.extend([
            "Ограничения досье:",
            block(limitations),
            "",
        ])

    return lines


def metadata_section(stages):
    """Метаданные контейнера и GPS — сильнейшие признаки места."""
    result = stage_result(stages, "metadata")
    tags = mapping(result.get("tags"))
    gps = records(result.get("gps"))
    stage = mapping(stages.get("metadata"))

    lines = [
        "## 5. Метаданные и GPS",
        "",
        "Теги контейнера не проверены на подлинность. "
        "GPS-тег может быть унаследован от другого файла "
        "или изменён, но остаётся самым точным признаком.",
        "",
    ]

    if not result:
        lines.extend([
            "Этап метаданных не выполнялся в этом задании.",
            "",
        ])
        return lines

    if stage.get("status") not in (None, "completed"):
        lines.extend([
            "Этап метаданных не завершён успешно:",
            block(stage.get("error") or stage.get("note") or ""),
            "",
        ])

    lines.extend([
        "Устройство:",
        block(result.get("device") or "не определено"),
        "",
        "Дата создания:",
        block(result.get("created_at") or "не определена"),
        "",
    ])

    if gps:
        lines.extend(["GPS из файла:", ""])

        for item in gps:
            lines.append(
                f"- {item.get('latitude')}, {item.get('longitude')}"
            )

        lines.append("")
    else:
        lines.extend([
            "GPS в метаданных не найден.",
            "",
        ])

    if tags:
        lines.extend([
            "Найденные теги:",
            json_block(tags),
            "",
        ])
    else:
        lines.extend([
            "Полезные теги не найдены. Установка ExifTool "
            "расширяет чтение метаданных, но не обязательна.",
            "",
        ])

    return lines


# ============================================================
# Генерация отчёта
# ============================================================

def render_report(job):
    stages = mapping(job.get("stages"))
    options = mapping(job.get("options"))

    observations = collect_observations(job)

    source_counts = Counter(
        str(item.get("source", "unknown"))
        for item in observations
    )

    review_counts = Counter(
        item.get("review", "unreviewed")
        for item in observations
    )

    prepare = mapping(stages.get("prepare"))
    prepared = mapping(prepare.get("result"))

    lines = [
        "# Отчёт о признаках места съёмки и извлечённой информации",
        "",
        "> Отчёт объединяет результаты анализаторов, включая "
        "GPS, метаданные и визуальные признаки. Географические "
        "гипотезы требуют ручной проверки и не являются "
        "подтверждённым адресом.",
        "",
        "## 1. Сведения о задании",
        "",
        json_block({
            "job_id": job.get("id"),
            "filename": job.get("name"),
            "status": job.get("status"),
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
            "report_generated_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "duration_seconds": prepared.get("duration"),
            "has_audio": prepared.get("has_audio"),
            "source_sha256": prepared.get("sha256"),
            "preview_artifact": prepared.get("preview"),
        }),
        "",
        "## 2. Параметры анализа",
        "",
        json_block(dict(options)),
        "",
        "## 3. Сводка",
        "",
        f"- Всего сохранённых наблюдений: {len(observations)}.",
        f"- Подтверждено пользователем: "
        f"{review_counts['accepted']}.",
        f"- Отклонено пользователем: "
        f"{review_counts['rejected']}.",
        f"- Не проверено: "
        f"{review_counts['unreviewed']}.",
        "",
        "Количество наблюдений по источникам:",
        json_block(dict(source_counts)),
        "",
        "Количество наблюдений не равно количеству "
        "уникальных объектов или независимых свидетельств.",
        "",
    ]

    lines.extend(location_dossier_section(stages))
    lines.extend(metadata_section(stages))

    lines.extend([
        "## 6. Состояние анализаторов",
        "",
    ])

    # ---------- Состояние этапов ----------

    for stage_name, raw_stage in stages.items():
        stage = mapping(raw_stage)
        result = mapping(stage.get("result"))

        status = stage.get("status", "unknown")
        history = stage.get("history")

        if isinstance(history, list):
            history_count = len(history)
        else:
            history_count = stage.get("history_count")

        lines.extend([
            f"### {STAGE_NAMES.get(stage_name, 'Другой этап')}",
            "",
            json_block({
                "stage_key": stage_name,
                "status": STATUS_NAMES.get(status, status),
                "observation_count": len(
                    records(stage.get("observations"))
                ),
                "run_id": stage.get("run_id"),
                "result_run_id": stage.get("result_run_id"),
                "previous_result_is_displayed": (
                    is_previous_result(stage)
                ),
                "history_count": history_count,
                "note": stage.get("note"),
                "result_note": result.get("note"),
                "error": stage.get("error"),
                "partial_errors": result.get("errors", []),
            }),
            "",
        ])

        # Сохраняем полезные поля уровня этапа:
        # язык, список кадров, интервалы сцен и т. п.
        # Тяжёлые блоки, повторяющие отдельные разделы,
        # не дублируем.
        excluded = {
            "observations",
            "errors",
            "note",
        }

        if stage_name == "location_evidence":
            excluded.update({"dossier", "artifact"})

        if stage_name == "metadata":
            excluded.update({"tags", "gps"})

        if stage_name == "audio_structure":
            excluded.add("windows")

        if stage_name == "speech":
            excluded.add("segments")

        if stage_name in (
            "ocr",
            "scene_objects",
            "visual_profile",
        ):
            excluded.add("frames")

        if stage_name == "scene_objects":
            excluded.add("unique_objects")

        stage_details = {
            key: value
            for key, value in result.items()
            if key not in excluded
        }

        if stage_details:
            lines.extend([
                "Дополнительные результаты этапа:",
                json_block(stage_details),
                "",
            ])

    # Явно отмечаем новые этапы, которых нет в старом задании.
    for stage_name in (
        "metadata",
        "audio_structure",
        "visual_profile",
        "scene_objects",
        "road_geometry",
        "location_evidence",
        "visual",
        "audio_events",
        "structure",
    ):
        if stage_name not in stages:
            lines.extend([
                f"### {STAGE_NAMES[stage_name]}",
                "",
                "Этап отсутствует в структуре этого задания. "
                "Это не означает, что соответствующих "
                "признаков нет в видео.",
                "",
            ])

    # ---------- Техническая информация ----------

    append_section(
        lines,
        "7. Технические сведения",
        select_items(observations, {"technical"}),
    )

    # ---------- Сцены ----------

    append_section(
        lines,
        "8. Сцены",
        select_items(observations, {"scene"}),
    )

    # ---------- Чистовая транскрипция ----------

    lines.extend([
        "## 9. Транскрипция для чтения",
        "",
        "Используется исправленный текст, если он сохранён. "
        "Отклонённые записи исключены только из этой версии "
        "транскрипции и сохранены в следующем разделе.",
        "",
    ])

    speech = select_items(observations, {"speech"})

    readable_speech = [
        item
        for item in speech
        if item.get("review") != "rejected"
    ]

    if not readable_speech:
        lines.extend([
            "Доступной транскрипции нет.",
            "",
        ])

    for item in readable_speech:
        lines.extend([
            f"### {interval(item)}",
            "",
        ])

        segments = records(
            mapping(item.get("data")).get("segments")
        )
        corrected = item.get("corrected_text")

        if corrected is not None and corrected != item.get("text"):
            lines.append(block(corrected))

        elif segments:
            for segment in segments[:500]:
                text = str(
                    segment.get("text", "")
                ).strip()

                if not text:
                    continue

                lines.append(
                    f"- `{timestamp(segment.get('start'))}`"
                    f" — {text}"
                )

            if len(segments) > 500:
                lines.append(
                    f"Показаны первые 500 из "
                    f"{len(segments)} реплик."
                )

        else:
            lines.append(block(effective_text(item)))

        lines.append("")

        if mapping(
            item.get("_provenance")
        ).get("previous_result"):
            lines.extend([
                "Примечание: результат предыдущей "
                "попытки этапа.",
                "",
            ])

    append_section(
        lines,
        "10. Речь — оригиналы и проверка",
        speech,
    )

    # ---------- OCR: сводка повторов ----------

    lines.extend([
        "## 11. Надписи — сводка повторений",
        "",
        "Группировка выполняется по совпадению текста "
        "после нормализации регистра и пробелов. "
        "Она не устанавливает идентичность объектов. "
        "Отклонённые записи исключены из группировки, "
        "но сохранены в подробном разделе.",
        "",
    ])

    ocr = select_items(observations, {"ocr"})
    groups = {}

    for item in ocr:
        if item.get("review") == "rejected":
            continue

        text = effective_text(item)

        if not text.strip():
            continue

        key = normalized_text(text)
        groups.setdefault(key, []).append(item)

    if not groups:
        lines.extend([
            "Нет надписей для группировки.",
            "",
        ])

    for number, items in enumerate(
        groups.values(),
        start=1,
    ):
        lines.extend([
            f"### Надпись {number}",
            "",
            block(effective_text(items[0])),
            "",
            f"Количество появлений в выборке: {len(items)}.",
            "",
            "Связанные наблюдения:",
            json_block([
                {
                    "observation_id": item.get("id"),
                    "time": timestamp(item.get("start")),
                    "original_text": item.get("text"),
                    "corrected_text": item.get(
                        "corrected_text"
                    ),
                    "recognition_score": item.get(
                        "recognition_score"
                    ),
                    "frame_artifact": item.get(
                        "frame_artifact"
                    ),
                    "crop_artifact": item.get("artifact"),
                    "previous_result": mapping(
                        item.get("_provenance")
                    ).get("previous_result"),
                }
                for item in items
            ]),
            "",
        ])

    append_section(
        lines,
        "12. Надписи — оригиналы и проверка",
        ocr,
    )

    # ---------- Визуальная сводка ----------

    visual = select_items(observations, {"visual"})

    object_items = [
        item
        for item in visual
        if mapping(item.get("data")).get("kind")
        == "object"
    ]

    category_counts = Counter(
        mapping(item.get("data")).get(
            "category", "unspecified"
        )
        for item in object_items
    )

    lines.extend([
        "## 13. Визуальные признаки — сводка категорий",
        "",
        "Учитываются записи об объектах, включая "
        "ещё не проверенные. Одна и та же вещь может "
        "присутствовать в нескольких наблюдениях.",
        "",
        json_block({
            CATEGORY_NAMES.get(category, category): count
            for category, count in category_counts.items()
        }),
        "",
    ])

    append_section(
        lines,
        "14. Визуальные признаки — подробности",
        visual,
    )

    # ---------- Визуальный профиль места ----------

    visual_profile = stage_result(stages, "visual_profile")
    profile = mapping(visual_profile.get("profile"))

    lines.extend([
        "## 15. Визуальный профиль места",
        "",
        "Освещённость, погода, сезон и тип ландшафта "
        "оценены по цвету и текстуре кадров. Это "
        "предварительные признаки, а не координаты.",
        "",
    ])

    if profile:
        lines.extend([
            json_block(profile),
            "",
        ])
    else:
        lines.extend([
            "Профиль не сформирован: этап «Визуальный "
            "профиль места» не завершён.",
            "",
        ])

    # ---------- Уникальные объекты ----------

    scene_result = stage_result(
        stages,
        "scene_objects",
    )

    scene_objects = records(
        scene_result.get("unique_objects")
    )

    if not scene_objects:
        scene_objects = unique_objects_from_frames(
            records(scene_result.get("frames"))
        )

    lines.extend([
        "## 16. Уникальные объекты и ориентиры",
        "",
        "Список типов объектов, найденных на кадрах видео. "
        "Модель размечает классы, а не отдельные экземпляры, "
        "поэтому один пункт может объединять несколько "
        "похожих объектов. Таймкод указывает на лучший кадр.",
        "",
    ])

    if scene_objects:
        for category in CATEGORY_ORDER:
            items = [
                item
                for item in scene_objects
                if item.get("category") == category
            ]

            if not items:
                continue

            lines.extend([
                f"### {CATEGORY_LABELS_RU.get(category, category)}",
                "",
            ])

            for item in items:
                lines.append(
                    f"- **{item.get('label_ru') or item.get('label')}**"
                    f" — {item.get('frame_count', 0)} кадр.; "
                    f"до {item.get('max_area_percent', 0)}% кадра; "
                    f"лучший кадр `{timestamp(item.get('best_timestamp'))}`."
                )

            lines.append("")
    else:
        lines.extend([
            "Уникальные объекты не найдены или этап "
            "«Объекты и признаки места» не завершён.",
            "",
        ])

    lines.extend(key_frames_section(stages, observations))

    append_section(
        lines,
        "18. Звуковая структура и звуковые события",
        select_items(
            observations,
            {"audio_structure", "audio_event"},
        ),
    )

    # ---------- Новые направления ----------

    append_section(
        lines,
        "19. Пространственные отношения",
        select_items(observations, {"relation"}),
    )

    append_section(
        lines,
        "20. Повторяющиеся надписи и визуальные совпадения",
        select_items(
            observations,
            {"reappearance", "sequence"},
        ),
    )

    append_section(
        lines,
        "21. Географические улики",
        select_items(observations, {"location_evidence"}),
    )

    append_section(
        lines,
        "22. Метаданные — наблюдения",
        select_items(observations, {"metadata"}),
    )

    # Не теряем новые типы наблюдений при расширении сервиса.
    other = [
        item
        for item in observations
        if item.get("source") not in KNOWN_SOURCES
    ]

    if other:
        append_section(
            lines,
            "Дополнительные наблюдения",
            other,
        )

    # ---------- Ограничения ----------

    lines.extend([
        "## 23. Ограничения и правила интерпретации",
        "",
        "- Отчёт содержит признаки и гипотезы, "
        "а не подтверждённые географические выводы.",
        "- GPS-тег файла может быть неточным, устаревшим "
        "или унаследованным от другого устройства.",
        "- Упоминание места в речи или надписи "
        "не устанавливает место съёмки.",
        "- Совпадение бренда, языка, валюты или телефона "
        "сужает круг стран, но не даёт адрес.",
        "- Визуальный профиль, звуковой фон и геометрия "
        "дороги — предварительные оценки.",
        "- Оригинальные результаты сохранены отдельно "
        "от пользовательских исправлений.",
        "- Отклонённые наблюдения оставлены в подробных "
        "разделах для прослеживаемости.",
        "- Таймкоды могут быть приблизительными.",
        "- Визуальные описания, рамки и отношения "
        "могут содержать ошибки модели.",
        "- Слева, справа, выше и ниже относятся "
        "к изображению, а не к сторонам света.",
        "- Перед и за — предварительные интерпретации "
        "глубины, не измерение расстояния.",
        "- Звуковые категории являются предварительными "
        "соответствиями; числовое сходство не является "
        "вероятностью события.",
        "- Похожие фрагменты не доказывают, что "
        "на них изображён один объект.",
        "- Порядок исследованных кадров не доказывает "
        "непрерывность движения или маршрута.",
        "- Повторяющиеся надписи не являются "
        "независимыми подтверждениями.",
        "- Отсутствие наблюдений не доказывает "
        "отсутствие информации в видео.",
        "- Изображения и аудио в Markdown не встроены. "
        "Пути артефактов — ссылки на локальное "
        "хранилище сервиса, не вложения в отчёт.",
        "- В основные разделы включены текущие "
        "доступные результаты этапов. Исторические "
        "попытки целиком повторно не включаются.",
        "",
    ])

    return "\n".join(lines).rstrip() + "\n"