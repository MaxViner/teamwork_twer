"""HTTP-клиент AI-провайдера.

Поддерживаются два совместимых способа вызова:

- Google Gemini (по умолчанию) — generateContent с картинкой в
  inline_data и необязательным поиском в интернете (google_search);
- OpenAI-совместимый chat/completions (OpenRouter, OpenAI).

Зависимостей нет: используется стандартный urllib. Ошибки
провайдера превращаются в понятные русские сообщения.
"""

import base64
import json
import urllib.error
import urllib.request

from app.services.aiService.config import get_settings


class AiNotConfigured(RuntimeError):
    """Провайдер не настроен: нет ключа."""


class AiServiceError(RuntimeError):
    """Провайдер ответил ошибкой или недоступен."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def not_configured_message() -> str:
    return (
        "AI-провайдер не настроен. Добавьте бесплатный ключ "
        "в backend/.env, например: AI_API_KEY=ваш_ключ "
        "(Google Gemini: https://aistudio.google.com/apikey). "
        "После сохранения перезапустите backend."
    )


def is_configured() -> bool:
    return bool(get_settings().get("api_key"))


def public_status() -> dict:
    settings = get_settings()

    return {
        "configured": bool(settings.get("api_key")),
        "provider": settings.get("provider"),
        "model": settings.get("model"),
        "models": settings.get("models") or [],
        "web_search": bool(settings.get("web_search")),
        "message": (
            "AI-провайдер настроен."
            if settings.get("api_key")
            else not_configured_message()
        ),
    }


def describe_image(
    image_bytes: bytes,
    mime_type: str,
    prompt: str,
    *,
    json_mode: bool = True,
) -> dict:
    """Отправить изображение и текстовый запрос мультимодальной модели."""

    settings = get_settings()

    if not settings["api_key"]:
        raise AiNotConfigured(not_configured_message())

    encoded = base64.b64encode(image_bytes).decode("ascii")

    if settings["provider"] == "gemini":
        parts = [
            {"text": prompt},
            {
                "inline_data": {
                    "mime_type": mime_type,
                    "data": encoded,
                }
            },
        ]

        return _gemini_generate(
            parts,
            settings,
            json_mode=json_mode,
        )

    if settings["provider"] in {"openai", "openrouter"}:
        data_url = f"data:{mime_type};base64,{encoded}"

        content = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": data_url},
            },
        ]

        return _openai_generate(
            content,
            settings,
            json_mode=json_mode,
        )

    raise AiServiceError(
        f"Неизвестный AI-провайдер: {settings['provider']}"
    )


def generate_text(
    prompt: str,
    *,
    system: str | None = None,
    json_mode: bool = False,
    web_search: bool = False,
) -> dict:
    """Текстовый запрос к модели. web_search включает grounding."""

    settings = get_settings()

    if not settings["api_key"]:
        raise AiNotConfigured(not_configured_message())

    if settings["provider"] == "gemini":
        return _gemini_generate(
            [{"text": prompt}],
            settings,
            system=system,
            json_mode=json_mode,
            web_search=web_search,
        )

    if settings["provider"] in {"openai", "openrouter"}:
        return _openai_generate(
            prompt,
            settings,
            system=system,
            json_mode=json_mode,
        )

    raise AiServiceError(
        f"Неизвестный AI-провайдер: {settings['provider']}"
    )


def _gemini_generate(
    parts: list[dict],
    settings: dict,
    *,
    system: str | None = None,
    json_mode: bool = False,
    web_search: bool = False,
) -> dict:
    body = {
        "contents": [
            {
                "role": "user",
                "parts": parts,
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 2048,
        },
    }

    if system:
        body["system_instruction"] = {
            "parts": [{"text": system}]
        }

    if json_mode:
        body["generationConfig"]["response_mime_type"] = (
            "application/json"
        )

    if web_search:
        body["tools"] = [{"google_search": {}}]

    models = settings.get("models") or [settings["model"]]
    last_error = None

    for model in models:
        url = (
            f"{settings['base_url']}/models/{model}"
            f":generateContent?key={settings['api_key']}"
        )

        try:
            payload = _post_json(
                url,
                body,
                timeout=settings["timeout"],
            )

        except AiServiceError as error:
            last_error = error

            # Устаревшая или недоступная модель — пробуем следующую.
            if error.status in {400, 404} and model != models[-1]:
                continue

            raise

        return _gemini_result(payload, settings, model)

    raise last_error or AiServiceError("AI-провайдер недоступен.")


def _gemini_result(payload: dict, settings: dict, model: str) -> dict:
    candidates = payload.get("candidates") or []

    if not candidates:
        raise AiServiceError(
            "AI-провайдер не вернул ответ."
        )

    candidate = candidates[0]
    chunks = (candidate.get("content") or {}).get("parts") or []
    text = "\n".join(
        str(chunk.get("text"))
        for chunk in chunks
        if chunk.get("text")
    ).strip()

    if not text:
        finish = candidate.get("finishReason")
        suffix = f" ({finish})" if finish else ""

        raise AiServiceError(
            f"AI-провайдер вернул пустой ответ{suffix}."
        )

    metadata = candidate.get("groundingMetadata") or {}
    sources = []

    for chunk in metadata.get("groundingChunks") or []:
        web = chunk.get("web") or {}
        url = web.get("uri")

        if not url:
            continue

        sources.append({
            "title": web.get("title") or url,
            "url": url,
        })

    return {
        "text": text,
        "sources": sources,
        "search_queries": metadata.get("webSearchQueries") or [],
        "provider": settings["provider"],
        "model": model,
    }


def _openai_generate(
    content,
    settings: dict,
    *,
    system: str | None = None,
    json_mode: bool = False,
) -> dict:
    body = {
        "model": settings["model"],
        "messages": [],
        "temperature": 0.2,
        "max_tokens": 2048,
    }

    if system:
        body["messages"].append({
            "role": "system",
            "content": system,
        })

    body["messages"].append({
        "role": "user",
        "content": content,
    })

    if json_mode:
        body["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {settings['api_key']}",
    }

    if settings["provider"] == "openrouter":
        headers["HTTP-Referer"] = "http://localhost"
        headers["X-Title"] = "video-service"

    payload = _post_json(
        f"{settings['base_url']}/chat/completions",
        body,
        timeout=settings["timeout"],
        headers=headers,
    )

    choices = payload.get("choices") or []

    if not choices:
        raise AiServiceError(
            "AI-провайдер не вернул ответ."
        )

    text = (
        (choices[0].get("message") or {}).get("content")
        or ""
    ).strip()

    if not text:
        raise AiServiceError(
            "AI-провайдер вернул пустой ответ."
        )

    return {
        "text": text,
        "sources": [],
        "search_queries": [],
        "provider": settings["provider"],
        "model": settings["model"],
    }


def _post_json(
    url: str,
    payload: dict,
    *,
    timeout: int,
    headers: dict | None = None,
) -> dict:
    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            **(headers or {}),
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:
            raw = response.read().decode(
                "utf-8",
                errors="replace",
            )

    except urllib.error.HTTPError as error:
        detail = error.read().decode(
            "utf-8",
            errors="replace",
        )

        raise AiServiceError(
            _friendly_http_error(error.code, detail),
            status=error.code,
        ) from None

    except urllib.error.URLError as error:
        raise AiServiceError(
            "Нет связи с AI-провайдером: "
            f"{error.reason}"
        ) from None

    except TimeoutError:
        raise AiServiceError(
            "AI-провайдер не ответил вовремя. "
            "Попробуйте ещё раз."
        ) from None

    try:
        return json.loads(raw)

    except json.JSONDecodeError:
        raise AiServiceError(
            "AI-провайдер вернул ответ не в формате JSON."
        ) from None


def _friendly_http_error(status: int, detail: str) -> str:
    message = detail

    try:
        parsed = json.loads(detail)
        message = (
            (parsed.get("error") or {}).get("message")
            or parsed.get("message")
            or detail
        )

    except (json.JSONDecodeError, AttributeError):
        pass

    message = " ".join(str(message).split())[:600]

    if status in {401, 403}:
        return (
            "AI-провайдер отклонил ключ "
            f"({status}): {message}"
        )

    if status == 429:
        return (
            "Лимит бесплатного AI-провайдера исчерпан "
            f"(429): {message}"
        )

    return f"Ошибка AI-провайдера ({status}): {message}"
