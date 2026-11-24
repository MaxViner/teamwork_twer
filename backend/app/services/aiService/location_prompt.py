"""Финальный поисковый промпт для агента-геолокатора.

Последний этап пайплайна. Собирает накопленный отчёт (улики речи и
OCR, ориентиры, дорогу, конспект, структуру, расшифровку, карту
гипотез), отправляет его AI-провайдеру и получает готовый промпт
для другого агента, который будет искать место съёмки.

Промпт — это задание на поиск, а не координаты. Сервис по-прежнему
не утверждает, что место найдено.
"""

import json

from app.services.aiService import client
from app.services.aiService.config import get_settings
from app.services.reportingService.reporting import render_evidence_json
from app.utils.errors import SkipStage
from app.utils.observations import observation


MAX_INPUT_CHARS = 24000

SYSTEM = """Ты — аналитик геолокации. Твоя задача — превратить
накопленный отчёт об анализе видео в один точный поисковый промпт
для другого AI-агента. Этот агент будет искать место съёмки по
описанию, поэтому промпт должен быть самодостаточным.

Требования к промпту:
- сформулируй его на русском языке, одним связным текстом;
- перечисли все сильные зацепки: регион и топонимы, надписи, речь,
  ориентиры, архитектуру, дорогу, ландшафт, транспорт, время года;
- отдели подтверждённые наблюдения от гипотез и сомнительных данных;
- явно укажи, что координаты не подтверждены и что нужно проверить
  по картам, панорамам и справочникам;
- предложи конкретные шаги поиска и список поисковых запросов;
- не выдумывай факты, адреса и координаты;
- не добавляй в ответ пояснений от себя — верни только текст промпта.
"""

PROMPT = """Ниже отчёт об анализе видео. Сформируй по нему
поисковый промпт для агента, который определит место съёмки.

ОТЧЁТ:
{report}
"""


def build_location_prompt(
    storage,
    stages: dict,
    progress,
) -> dict:
    """Собрать промпт по stages и сохранить его в результате этапа."""

    settings = get_settings()

    if not settings["api_key"]:
        raise SkipStage(
            "AI-провайдер не настроен: добавьте AI_API_KEY "
            "в backend/.env, чтобы сформировать поисковый промпт."
        )

    progress(5, "Собираю отчёт для AI")

    job = _job_view(storage, stages)

    try:
        evidence = render_evidence_json(job)

    except Exception as error:
        evidence = _fallback_evidence(
            stages,
            str(error),
        )

    compact = _compact(evidence)

    progress(35, "Отправляю отчёт в AI")

    answer = client.generate_text(
        PROMPT.format(
            report=json.dumps(
                compact,
                ensure_ascii=False,
                indent=2,
            )
        ),
        system=SYSTEM,
    )

    prompt = str(answer.get("text") or "").strip()

    if not prompt:
        raise RuntimeError(
            "AI вернул пустой поисковый промпт."
        )

    progress(100, "Поисковый промпт готов")

    return {
        "prompt": prompt,
        "provider": answer.get("provider"),
        "model": answer.get("model"),
        "sources": answer.get("sources") or [],
        "input": {
            "text_clues": len(compact.get("text_clues") or []),
            "transcript_segments": len(
                (compact.get("transcript") or {}).get("segments")
                or []
            ),
            "landmarks": len(
                (compact.get("landmarks") or {}).get("items")
                or []
            ),
            "road_episodes": len(
                (compact.get("road") or {}).get("episodes")
                or []
            ),
        },
        "observations": [
            observation(
                source="ai_prompt",
                start=0.0,
                end=0.0,
                text=prompt,
                extractor="ai-service",
                data={
                    "kind": "location_search_prompt",
                    "provider": answer.get("provider"),
                    "model": answer.get("model"),
                    "sources": answer.get("sources") or [],
                    "is_coordinates": False,
                },
            )
        ],
        "note": (
            "Промпт сформирован AI по накопленным уликам. "
            "Это задание для поиска, а не найденные координаты."
        ),
    }


def _job_view(storage, stages: dict) -> dict:
    """Минимальное представление задания для render_evidence_json."""

    name = None

    try:
        if storage.job_json.is_file():
            payload = json.loads(
                storage.job_json.read_text(encoding="utf-8")
            )
            name = payload.get("name")

    except (OSError, ValueError):
        name = None

    return {
        "id": storage.folder.name,
        "name": name,
        "stages": stages,
    }


def _fallback_evidence(stages: dict, error: str) -> dict:
    summary = (
        (stages.get("summary") or {}).get("result") or {}
    )
    landmarks = (
        (stages.get("landmarks") or {}).get("result") or {}
    )
    objects = (
        (stages.get("scene_objects") or {}).get("result") or {}
    )

    return {
        "summary": {
            "overview": summary.get("overview"),
            "topics": summary.get("topics") or [],
            "theses": summary.get("theses") or [],
        },
        "landmarks": {
            "items": landmarks.get("landmarks") or [],
            "geometry": landmarks.get("geometry") or {},
        },
        "unique_objects": objects.get("unique_objects") or [],
        "text_clues": [],
        "road": {},
        "transcript": {},
        "structure": {},
        "limitations": [
            "Полный отчёт собрать не удалось: "
            f"{error[:300]}",
        ],
    }


def _compact(evidence: dict) -> dict:
    """Оставить самое полезное, чтобы не превысить лимит токенов."""

    geo = evidence.get("geo_scene") or {}
    map_queries = geo.get("map_queries") or {}
    transcript = evidence.get("transcript") or {}
    structure = evidence.get("structure") or {}
    road = evidence.get("road") or {}
    landmarks = evidence.get("landmarks") or {}

    compact = {
        "video": evidence.get("video"),
        "coordinates": evidence.get("coordinates"),
        "summary": evidence.get("summary"),
        "text_clues": _trim_clues(
            evidence.get("text_clues") or []
        ),
        "road": {
            "episodes": _trim_list(
                road.get("episodes") or [],
                8,
            ),
            "schematic": road.get("schematic") or {},
        },
        "landmarks": {
            "items": _trim_list(
                landmarks.get("items") or [],
                20,
            ),
            "geometry": landmarks.get("geometry") or {},
        },
        "faces": {
            "available": bool(
                (evidence.get("faces") or {}).get("available")
            ),
            "face_count": (
                evidence.get("faces") or {}
            ).get("face_count"),
        },
        "structure": {
            "sections": _trim_list(
                structure.get("sections") or [],
                12,
            ),
        },
        "transcript": {
            "language": transcript.get("language"),
            "speaker_method": transcript.get("speaker_method"),
            "turn_summary": transcript.get("turn_summary"),
            "segments": _trim_list(
                transcript.get("segments") or [],
                60,
            ),
        },
        "map_queries": map_queries,
        "limitations": evidence.get("limitations") or [],
    }

    if len(json.dumps(compact, ensure_ascii=False)) > MAX_INPUT_CHARS:
        compact["text_clues"] = compact["text_clues"][:20]
        compact["transcript"]["segments"] = (
            compact["transcript"]["segments"][:30]
        )
        compact["road"]["episodes"] = (
            compact["road"]["episodes"][:5]
        )
        compact["landmarks"]["items"] = (
            compact["landmarks"]["items"][:12]
        )

    return compact


def _trim_list(items: list, limit: int) -> list:
    return [
        item for item in items[:limit]
        if isinstance(item, (dict, list, str, int, float))
    ]


def _trim_clues(items: list) -> list:
    trimmed = []

    for item in items[:40]:
        if not isinstance(item, dict):
            continue

        copy = dict(item)

        if copy.get("excerpt"):
            copy["excerpt"] = str(copy["excerpt"])[:280]

        trimmed.append(copy)

    return trimmed
