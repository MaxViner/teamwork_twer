"""Универсальный HTTP-клиент AI-провайдера.

Поддерживаются два протокола:

1. OpenAI-compatible:
   POST {base_url}/chat/completions

   Подходит для OpenAI, Plnex/APInex, OpenRouter
   и других совместимых сервисов.

2. Anthropic Messages:
   POST {base_url}/v1/messages

   Подходит для ZvenoAI и Anthropic-совместимых шлюзов.

Провайдер, протокол, ключ, модели и base URL
задаются только через backend/.env.
"""


import base64
import json
import socket
import urllib.error
import urllib.request


from app.services.aiService.aiConfig import get_settings



class AiNotConfigured(RuntimeError):
    """Провайдер не настроен: нет ключа или модели."""



class AiServiceError(RuntimeError):
    """Провайдер ответил ошибкой или недоступен."""


    def __init__(
        self,
        message: str,
        status: int | None = None,
    ):
        super().__init__(message)
        self.status = status



def not_configured_message() -> str:
    return (
        "AI-провайдер не настроен. Добавьте в backend/.env:\n\n"
        "Для ZvenoAI:\n"
        "AI_API_PROVIDER=zveno\n"
        "AI_API_PROTOCOL=openai\n"
        "ZVENO_API_KEY=ваш_ключ\n"
        "AI_CHAT_MODEL=nvidia/nemotron-3.5-lightning:free\n"
        "AI_VISION_MODEL=nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free\n"
        "AI_API_BASE_URL=https://api.zveno.ai/v1\n\n"
        "Для OpenAI:\n"
        "AI_API_PROVIDER=openai\n"
        "AI_API_PROTOCOL=openai\n"
        "OPENAI_API_KEY=ваш_ключ\n"
        "AI_CHAT_MODEL=gpt-4o-mini\n"
        "AI_VISION_MODEL=gpt-4o\n"
        "AI_API_BASE_URL=https://api.openai.com/v1\n\n"
        "Для Plnex/APInex:\n"
        "AI_API_PROVIDER=plnex\n"
        "AI_API_PROTOCOL=openai\n"
        "PLNEX_API_KEY=ваш_ключ\n"
        "AI_CHAT_MODEL=gemini/3.8-flash\n"
        "AI_VISION_MODEL=gemini/3.8-flash\n"
        "AI_API_BASE_URL=https://api.apinex.bond/v1\n\n"
        "Для OpenRouter:\n"
        "AI_API_PROVIDER=openrouter\n"
        "AI_API_PROTOCOL=openai\n"
        "OPENROUTER_API_KEY=ваш_ключ\n"
        "AI_CHAT_MODEL=particle-ai/particle-1:free\n"
        "AI_VISION_MODEL=inclusionai/ling-3.2-flash:free\n"
        "AI_API_BASE_URL=https://openrouter.ai/api/v1\n\n"
        "После сохранения .env перезапустите backend."
    )



def is_configured() -> bool:
    """Проверить, что заданы ключ и хотя бы одна модель."""


    settings = get_settings()


    has_key = bool(
        settings.get("api_key")
    )


    has_model = any(
        settings.get(name)
        for name in (
            "model",
            "chat_model",
            "vision_model",
        )
    )


    return bool(
        has_key
        and has_model
    )



def public_status() -> dict:
    """Статус AI-сервиса для frontend."""


    settings = get_settings()
    configured = is_configured()


    return {
        "configured": configured,
        "provider": settings.get("provider"),
        "protocol": settings.get("protocol"),
        "model": settings.get("model"),
        "chat_model": settings.get("chat_model"),
        "vision_model": settings.get("vision_model"),
        "models": settings.get("models") or [],
        "base_url": settings.get("base_url"),
        "web_search": False,
        "message": (
            "AI-провайдер настроен."
            if configured
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
    """Отправить изображение и текстовый запрос провайдеру."""


    settings = get_settings()


    if not is_configured():
        raise AiNotConfigured(
            not_configured_message()
        )


    encoded = base64.b64encode(
        image_bytes,
    ).decode("ascii")


    data_url = (
        f"data:{mime_type};base64,{encoded}"
    )


    content = [
        {
            "type": "text",
            "text": prompt,
        },
        {
            "type": "image_url",
            "image_url": {
                "url": data_url,
            },
        },
    ]


    vision_settings = dict(settings)
    vision_settings["model"] = (
        settings.get("vision_model")
        or settings.get("model")
    )


    try:
        return _chat_completion(
            content=content,
            settings=vision_settings,
            json_mode=json_mode,
        )


    except AiServiceError as error:
        message = str(error).lower()


        if (
            "image" in message
            or "vision" in message
            or "multimodal" in message
            or error.status == 400
        ):
            raise AiServiceError(
                "Модель "
                f"'{vision_settings['model']}' "
                "не приняла изображение. "
                "Выберите модель с поддержкой vision "
                "в переменной AI_VISION_MODEL.",
                status=error.status,
            ) from None


        raise



def generate_text(
    prompt: str,
    *,
    system: str | None = None,
    json_mode: bool = False,
    web_search: bool = False,
) -> dict:
    """Текстовый запрос провайдеру."""


    settings = get_settings()


    if not is_configured():
        raise AiNotConfigured(
            not_configured_message()
        )


    chat_settings = dict(settings)
    chat_settings["model"] = (
        settings.get("chat_model")
        or settings.get("model")
    )


    return _chat_completion(
        content=prompt,
        settings=chat_settings,
        system=system,
        json_mode=json_mode,
    )



def _chat_completion(
    content,
    settings: dict,
    *,
    system: str | None = None,
    json_mode: bool = False,
) -> dict:
    """Выбрать протокол и выполнить запрос."""


    protocol = settings.get(
        "protocol",
        "openai",
    )


    if protocol == "anthropic":
        return _anthropic_messages(
            content=content,
            settings=settings,
            system=system,
        )


    return _openai_chat_completions(
        content=content,
        settings=settings,
        system=system,
        json_mode=json_mode,
    )



def _openai_chat_completions(
    content,
    settings: dict,
    *,
    system: str | None = None,
    json_mode: bool = False,
) -> dict:
    """OpenAI-compatible Chat Completions."""


    messages = []


    if system:
        messages.append({
            "role": "system",
            "content": system,
        })


    messages.append({
        "role": "user",
        "content": content,
    })


    body = {
        "model": settings["model"],
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 2048,
    }


    if json_mode:
        body["response_format"] = {
            "type": "json_object",
        }


    payload = _post_json(
        url=(
            f"{settings['base_url']}"
            "/chat/completions"
        ),
        payload=body,
        timeout=settings["timeout"],
        headers={
            "Authorization": (
                f"Bearer {settings['api_key']}"
            ),
        },
    )


    choices = payload.get("choices") or []


    if not choices:
        raise AiServiceError(
            "AI-провайдер не вернул ответ."
        )


    message = choices[0].get("message") or {}
    text = (message.get("content") or "").strip()


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



def _anthropic_messages(
    content,
    settings: dict,
    *,
    system: str | None = None,
) -> dict:
    """Anthropic Messages API, например ZvenoAI."""


    user_content = _to_anthropic_content(
        content,
    )


    messages = [
        {
            "role": "user",
            "content": user_content,
        }
    ]


    body = {
        "model": settings["model"],
        "messages": messages,
        "max_tokens": 2048,
        "temperature": 0.2,
    }


    if system:
        body["system"] = system


    payload = _post_json(
        url=(
            f"{settings['base_url']}"
            "/v1/messages"
        ),
        payload=body,
        timeout=settings["timeout"],
        headers={
            "Authorization": (
                f"Bearer {settings['api_key']}"
            ),
            "anthropic-version": "2023-06-01",
        },
    )


    return _parse_anthropic_response(
        payload=payload,
        settings=settings,
    )



def _to_anthropic_content(
    content,
) -> list | str:
    """Преобразовать content в формат Anthropic Messages."""


    if isinstance(content, str):
        return content


    blocks = []


    for item in content:
        item_type = item.get("type")


        if item_type == "text":
            blocks.append({
                "type": "text",
                "text": item.get("text", ""),
            })


        elif item_type == "image_url":
            url = (
                (item.get("image_url") or {})
                .get("url", "")
            )


            if not url.startswith("data:"):
                raise AiServiceError(
                    "Anthropic-провайдер принимает "
                    "только Base64 data URL."
                )


            try:
                header, encoded = url.split(
                    ",",
                    1,
                )


            except ValueError:
                raise AiServiceError(
                    "Некорректный Base64 data URL."
                ) from None


            media_type = header.replace(
                "data:",
                "",
            ).replace(
                ";base64",
                "",
            )


            blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": encoded,
                },
            })


    if not blocks:
        raise AiServiceError(
            "Пустой content для Anthropic-запроса."
        )


    return blocks



def _parse_anthropic_response(
    payload: dict,
    settings: dict,
) -> dict:
    """Извлечь текст из ответа Anthropic Messages API."""


    if payload.get("type") == "error":
        error = payload.get("error") or {}


        raise AiServiceError(
            "Ошибка AI-провайдера: "
            f"{error.get('message') or payload}",
        )


    content_blocks = payload.get("content") or []
    text_parts = []


    for block in content_blocks:
        if block.get("type") == "text":
            text_parts.append(
                block.get("text", "")
            )


    text = "\n".join(
        part.strip()
        for part in text_parts
        if part.strip()
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
    """Выполнить POST-запрос и разобрать JSON."""


    data = json.dumps(
        payload,
    ).encode("utf-8")


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
            _friendly_http_error(
                error.code,
                detail,
            ),
            status=error.code,
        ) from None


    except urllib.error.URLError as error:
        raise AiServiceError(
            "Нет связи с AI-провайдером: "
            f"{error.reason}"
        ) from None


    except (TimeoutError, socket.timeout):
        raise AiServiceError(
            "Таймаут запроса к AI-провайдеру. "
            "Возможно, изображение слишком большое, "
            "модель перегружена или сеть медленная. "
            "Увеличьте AI_API_TIMEOUT или уменьшите файл."
        ) from None


    try:
        return json.loads(raw)


    except json.JSONDecodeError:
        raise AiServiceError(
            "AI-провайдер вернул ответ "
            "не в формате JSON."
        ) from None



def _friendly_http_error(
    status: int,
    detail: str,
) -> str:
    """Сделать ошибку провайдера понятной."""


    message = detail


    try:
        parsed = json.loads(detail)


        message = (
            (parsed.get("error") or {}).get("message")
            or parsed.get("message")
            or detail
        )


    except (
        json.JSONDecodeError,
        AttributeError,
    ):
        pass


    message = " ".join(
        str(message).split(),
    )[:600]


    if status == 402:
        return (
            "Провайдер требует пополнить баланс или "
            f"активировать квоту: {message}"
        )


    if status in {401, 403}:
        return (
            "Провайдер отклонил ключ "
            f"({status}): {message}"
        )


    if status == 404:
        return (
            "Модель или endpoint не найдены "
            f"(404): {message}"
        )


    if status == 429:
        return (
            "Лимит запросов или токенов исчерпан "
            f"(429): {message}"
        )


    if status == 503:
        return (
            "AI-провайдер временно недоступен "
            f"(503): {message}"
        )


    return (
        f"Ошибка AI-провайдера ({status}): {message}"
    )