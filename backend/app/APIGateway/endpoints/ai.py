"""Тестовые AI endpoints."""


import json

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    UploadFile,
)

from pydantic import BaseModel


from app.services.aiService import client as ai_client


router = APIRouter(prefix="/api")



class DevChatRequest(BaseModel):
    message: str
    web_search: bool = False
    system: str | None = None



@router.get("/ai/status")
def ai_status():
    return ai_client.public_status()



@router.post("/dev/vision/describe")
async def dev_vision_describe(
    file: UploadFile = File(...),
    prompt: str = Form(""),
):
    allowed = {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/heic",
        "image/heif",
    }


    mime_type = (
        file.content_type or "image/jpeg"
    ).lower()


    if mime_type not in allowed:
        raise HTTPException(
            400,
            "Поддерживаются изображения JPEG, PNG, "
            "WebP и HEIC/HEIF.",
        )


    image_bytes = await file.read()


    if not image_bytes:
        raise HTTPException(
            400,
            "Файл изображения пустой.",
        )


    if len(image_bytes) > 15 * 1024 * 1024:
        raise HTTPException(
            413,
            "Максимальный размер изображения — 15 МБ.",
        )


    if not ai_client.is_configured():
        raise HTTPException(
            503,
            ai_client.not_configured_message(),
        )


    user_prompt = prompt.strip() or (
        "Проанализируй изображение для геолокационного поиска. "
        "Верни JSON со следующими полями: "
        "short_description, detailed_description, "
        "main_objects, visible_text, location_clues, "
        "likely_place_types, search_queries, warnings."
    )


    try:
        result = ai_client.describe_image(
            image_bytes=image_bytes,
            mime_type=mime_type,
            prompt=user_prompt,
            json_mode=True,
        )


    except ai_client.AiNotConfigured as error:
        raise HTTPException(
            503,
            str(error),
        ) from None


    except ai_client.AiServiceError as error:
        raise HTTPException(
            502,
            str(error),
        ) from None


    except Exception as error:
        raise HTTPException(
            500,
            "Не удалось проанализировать изображение: "
            f"{str(error)[:500]}",
        ) from None


    parsed = _safe_json(
        result.get("text", ""),
    )


    return {
        "provider": result.get("provider"),
        "model": result.get("model"),
        "analysis": parsed or result.get("text"),
        "raw_text": result.get("text"),
        "sources": result.get("sources", []),
        "search_queries": result.get(
            "search_queries",
            [],
        ),
    }



@router.post("/dev/ai/chat")
def dev_ai_chat(
    request: DevChatRequest,
):
    message = request.message.strip()


    if not message:
        raise HTTPException(
            400,
            "Сообщение пустое.",
        )


    if not ai_client.is_configured():
        raise HTTPException(
            503,
            ai_client.not_configured_message(),
        )


    system = request.system or (
        "Ты — аккуратный аналитический ассистент. "
        "Отвечай по-русски, ясно и по существу. "
        "Если информации недостаточно, прямо скажи об этом."
    )


    try:
        result = ai_client.generate_text(
            prompt=message,
            system=system,
            web_search=request.web_search,
        )


    except ai_client.AiNotConfigured as error:
        raise HTTPException(
            503,
            str(error),
        ) from None


    except ai_client.AiServiceError as error:
        raise HTTPException(
            502,
            str(error),
        ) from None


    except Exception as error:
        raise HTTPException(
            500,
            "Не удалось получить ответ AI: "
            f"{str(error)[:500]}",
        ) from None


    return {
        "provider": result.get("provider"),
        "model": result.get("model"),
        "answer": result.get("text"),
        "sources": result.get("sources", []),
        "search_queries": result.get(
            "search_queries",
            [],
        ),
    }



def _safe_json(text: str):
    try:
        value = json.loads(text)


        return (
            value
            if isinstance(value, dict)
            else None
        )


    except (
        json.JSONDecodeError,
        TypeError,
    ):
        return None