import json
import math
import re
import unicodedata

from collections import Counter
from datetime import datetime, timezone


# ============================================================
# Названия этапов и типов наблюдений
# ============================================================

STAGE_NAMES = {
    "prepare": "Подготовка видео",
    "metadata": "Метаданные",
    "scenes": "Разделение на сцены",
    "speech": "Распознавание речи",
    "ocr": "Распознавание надписей",
    "visual": "Визуальные признаки",
    "audio_events": "Звуковые события",
    "structure": "Структура и повторения",
}

SOURCE_NAMES = {
    "technical": "Технические сведения",
    "scene": "Сцена",
    "speech": "Речь",
    "ocr": "Надпись",
    "visual": "Визуальное наблюдение",
    "relation": "Пространственное отношение",
    "audio_event": "Звуковое событие",
    "sequence": "Последовательность",
    "reappearance": "Визуальное сходство объектов",
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
    дублировать результаты. Географические метаданные исключены.
    """
    observations = []

    for stage_name, raw_stage in mapping(
        job.get("stages")
    ).items():
        if stage_name == "metadata":
            continue

        stage = mapping(raw_stage)

        for original in records(stage.get("observations")):
            if original.get("source") == "metadata":
                continue

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

    if item.get("data"):
        lines.extend([
            "Дополнительные данные анализатора:",
            json_block(item["data"]),
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
        "# Общий отчёт об извлечённой информации из видео",
        "",
        "> Отчёт объединяет сохранённые результаты анализаторов. "
        "Географические гипотезы, поиск места съёмки, "
        "геокодирование и GPS в него не входят.",
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
        json_block({
            key: value
            for key, value in options.items()
            if key != "metadata"
        }),
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
        "## 4. Состояние анализаторов",
        "",
    ]

    # ---------- Состояние этапов ----------

    for stage_name, raw_stage in stages.items():
        if stage_name == "metadata":
            continue

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
        stage_details = {
            key: value
            for key, value in result.items()
            if key not in (
                "observations",
                "errors",
                "note",
            )
        }

        if stage_details:
            lines.extend([
                "Дополнительные результаты этапа:",
                json_block(stage_details),
                "",
            ])

    # Явно отмечаем новые этапы, которых нет в старом задании.
    for stage_name in (
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
        "5. Технические сведения",
        select_items(observations, {"technical"}),
    )

    # ---------- Сцены ----------

    append_section(
        lines,
        "6. Сцены",
        select_items(observations, {"scene"}),
    )

    # ---------- Чистовая транскрипция ----------

    lines.extend([
        "## 7. Транскрипция для чтения",
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
            block(effective_text(item)),
            "",
        ])

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
        "8. Речь — оригиналы и проверка",
        speech,
    )

    # ---------- OCR: сводка повторов ----------

    lines.extend([
        "## 9. Надписи — сводка повторений",
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
        "10. Надписи — оригиналы и проверка",
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
        "## 11. Визуальные признаки — сводка категорий",
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
        "12. Визуальные признаки — подробности",
        visual,
    )

    # ---------- Новые направления ----------

    append_section(
        lines,
        "13. Пространственные отношения",
        select_items(observations, {"relation"}),
    )

    append_section(
        lines,
        "14. Звуковые события",
        select_items(observations, {"audio_event"}),
    )

    append_section(
        lines,
        "15. Порядок появления объектов и кадров",
        select_items(observations, {"sequence"}),
    )

    append_section(
        lines,
        "16. Возможные повторные появления объектов",
        select_items(observations, {"reappearance"}),
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
        "## 17. Ограничения и правила интерпретации",
        "",
        "- Отчёт содержит результаты извлечения, "
        "а не подтверждённые географические выводы.",
        "- GPS и этап географических метаданных исключены.",
        "- Упоминание места в речи или надписи "
        "не устанавливает место съёмки.",
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