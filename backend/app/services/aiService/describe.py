"""AI-описание уникального объекта по кадру.

Пользователь нажимает «Получить AI описание» на карточке объекта.
Берём лучший кадр, вырезаем область объекта по bbox (если он есть),
отправляем мультимодальной модели и просим вернуть строгий JSON:
краткое описание, возможную идентификацию, признаки, гипотезы о
месте и поисковые запросы.

Дополнительно, если включён веб-поиск, модель ищет похожие объекты
в интернете и возвращает ссылки-источники. Это приближение к
обратному поиску по фото: сам кадр в поисковик не загружается.
"""

import json
import re
from datetime import datetime, timezone
from io import BytesIO

from PIL import Image

from app.services.aiService import client
from app.services.aiService.config import get_settings
from app.storage import StorageService


MAX_IMAGE_SIDE = 1024
MAX_QUERY_CHARS = 900

DESCRIPTION_PROMPT = """Ты — эксперт по визуальной геолокации и распознаванию
объектов. На изображении фрагмент кадра из видео. Модель ранее отнесла
его к классу «{label}» (категория: {category}); это лишь подсказка, а не факт.

Задача:
1. Опиши, что видно на изображении, простыми словами.
2. Если объект узнаваем (здание, памятник, вывеска, транспорт, природная
   достопримечательность), назови его как можно точнее.
3. Перечисли визуальные признаки, которые помогут найти место:
   архитектура, надписи, язык вывесок, дорожные знаки, ландшафт, транспорт,
   стиль застройки.
4. Предложи 2–5 гипотез о стране / регионе / городе. Указывай уверенность
   low, medium или high и обязательно объясняй, на каком признаке она
   основана. Если оснований нет — не придумывай.
5. Дай 3–5 поисковых запросов (на русском и английском), по которым можно
   искать этот объект или похожие места.

Не выдумывай координаты и точные адреса. Не выдавай догадку за факт.
Верни ТОЛЬКО JSON без markdown-обёртки:
{{
  "summary": "краткое описание изображения",
  "identification": "что это за объект или место, если узнаётся",
  "features": ["признак 1", "признак 2"],
  "place_hypotheses": [
    {{"place": "страна/регион/город", "confidence": "low|medium|high", "reason": "почему"}}
  ],
  "search_queries": ["запрос 1", "запрос 2"],
  "caveats": ["ограничение или сомнение"]
}}"""

SEARCH_PROMPT = """Ты помогаешь определить место съёмки по описанию объекта
или кадра. Используй поиск в интернете и найди похожие объекты, здания,
памятники или места. Не выдумывай факты и ссылки.

Верни краткий отчёт:
1) какие конкретные объекты или места совпадают с описанием;
2) вероятные страны / регионы / города;
3) какие источники это подтверждают (названия и ссылки, если есть);
4) чего не хватает для уверенного вывода.

ОПИСАНИЕ КАДРА:
{description}"""


def find_unique_object(stage: dict, label: str) -> dict | None:
    """Найти объект в результате этапа scene_objects по метке."""

    result = (stage or {}).get("result") or {}

    for item in result.get("unique_objects") or []:
        if not isinstance(item, dict):
            continue

        if str(item.get("label")) == str(label):
            return item

    return None


def describe_unique_object(
    storage: StorageService,
    item: dict,
    result: dict,
) -> dict:
    """Получить AI-описание объекта. Возвращает готовый словарь."""

    settings = get_settings()

    if not settings["api_key"]:
        raise client.AiNotConfigured(
            client.not_configured_message()
        )

    artifact, bbox = _object_frame(result, item)

    if not artifact:
        raise ValueError(
            "У объекта нет сохранённого кадра."
        )

    image_bytes, mime_type = _image_payload(
        storage,
        artifact,
        bbox,
    )

    prompt = DESCRIPTION_PROMPT.format(
        label=item.get("label_ru") or item.get("label") or "объект",
        category=item.get("category") or "other",
    )

    answer = client.describe_image(
        image_bytes,
        mime_type,
        prompt,
        json_mode=True,
    )

    description = _normalize(_parse_json(answer["text"]))
    description["provider"] = answer["provider"]
    description["model"] = answer["model"]
    description["created_at"] = datetime.now(
        timezone.utc
    ).isoformat()
    description["sources"] = answer.get("sources") or []
    description["web_summary"] = ""

    if settings.get("web_search"):
        try:
            web = _web_search(description)
        except client.AiServiceError:
            web = None

        if web:
            description["web_summary"] = web["text"][:4000]
            description["sources"] = web.get("sources") or []

    return {
        "description": description,
        "image": {
            "artifact": artifact,
            "timestamp": item.get("best_timestamp"),
        },
    }


def _object_frame(result: dict, item: dict) -> tuple[str | None, list | None]:
    artifact = item.get("best_frame")

    if not artifact:
        return None, None

    for frame in result.get("frames") or []:
        if not isinstance(frame, dict):
            continue

        if frame.get("artifact") != artifact:
            continue

        for found in frame.get("objects") or []:
            if not isinstance(found, dict):
                continue

            if found.get("label") != item.get("label"):
                continue

            bbox = found.get("bbox")

            if (
                isinstance(bbox, list)
                and len(bbox) == 4
            ):
                return artifact, bbox

        return artifact, None

    return artifact, None


def _image_payload(
    storage: StorageService,
    artifact: str,
    bbox: list | None,
) -> tuple[bytes, str]:
    path = storage.resolve(artifact)

    if not path.is_file():
        raise ValueError(
            "Кадр объекта не найден на диске."
        )

    with Image.open(path) as source:
        image = source.convert("RGB")

        if bbox:
            image = _crop(image, bbox)

        image.thumbnail(
            (MAX_IMAGE_SIDE, MAX_IMAGE_SIDE),
            Image.LANCZOS,
        )

        buffer = BytesIO()
        image.save(
            buffer,
            format="JPEG",
            quality=88,
            optimize=True,
        )

    return buffer.getvalue(), "image/jpeg"


def _crop(image: Image.Image, bbox: list) -> Image.Image:
    width, height = image.size
    padding = 0.04

    try:
        x1, y1, x2, y2 = [
            max(0.0, min(1.0, float(value)))
            for value in bbox
        ]

    except (TypeError, ValueError):
        return image

    left = int(max(0.0, x1 - padding) * width)
    top = int(max(0.0, y1 - padding) * height)
    right = int(min(1.0, x2 + padding) * width)
    bottom = int(min(1.0, y2 + padding) * height)

    if right - left < 8 or bottom - top < 8:
        return image

    return image.crop((left, top, right, bottom))


def _parse_json(text: str) -> dict:
    cleaned = str(text or "").strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(
            r"^```[a-zA-Z]*\s*",
            "",
            cleaned,
        )
        cleaned = re.sub(
            r"\s*```$",
            "",
            cleaned,
        )

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start >= 0 and end > start:
        try:
            parsed = json.loads(
                cleaned[start:end + 1]
            )

            if isinstance(parsed, dict):
                return parsed

        except json.JSONDecodeError:
            pass

    return {"summary": cleaned[:4000]}


def _normalize(value: dict) -> dict:
    def text(key: str) -> str:
        raw = value.get(key)
        return " ".join(str(raw).split()) if raw else ""

    def strings(key: str) -> list[str]:
        raw = value.get(key)
        items = raw if isinstance(raw, list) else []
        return [
            " ".join(str(item).split())
            for item in items
            if str(item).strip()
        ][:12]

    hypotheses = []

    raw_hypotheses = value.get("place_hypotheses")

    if isinstance(raw_hypotheses, list):
        for item in raw_hypotheses[:8]:
            if not isinstance(item, dict):
                continue

            place = " ".join(
                str(item.get("place") or "").split()
            )

            if not place:
                continue

            confidence = str(
                item.get("confidence") or "low"
            ).lower()

            if confidence not in {"low", "medium", "high"}:
                confidence = "low"

            hypotheses.append({
                "place": place[:300],
                "confidence": confidence,
                "reason": " ".join(
                    str(item.get("reason") or "").split()
                )[:600],
            })

    return {
        "summary": text("summary")[:4000],
        "identification": text("identification")[:1000],
        "features": strings("features"),
        "place_hypotheses": hypotheses,
        "search_queries": strings("search_queries"),
        "caveats": strings("caveats"),
    }


def _web_search(description: dict) -> dict | None:
    parts = [
        description.get("identification"),
        description.get("summary"),
        "; ".join(description.get("features") or []),
    ]

    query = " ".join(
        part for part in parts if part
    ).strip()

    if not query:
        return None

    prompt = SEARCH_PROMPT.format(
        description=query[:MAX_QUERY_CHARS],
    )

    return client.generate_text(
        prompt,
        web_search=True,
    )
