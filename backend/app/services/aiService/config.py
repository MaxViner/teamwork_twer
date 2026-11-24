"""Настройки AI-сервиса.

Ключ и провайдер читаются из переменных окружения. Чтобы не
добавлять зависимость python-dotenv, простой файл backend/.env
читается вручную: строки KEY=VALUE, пустые строки и комментарии
пропускаются.

Бесплатный ключ Google Gemini: https://aistudio.google.com/apikey
Другой вариант — OpenRouter с бесплатными моделями:
AI_API_PROVIDER=openrouter и OPENROUTER_API_KEY=...
"""

import os
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[3]
ENV_FILE = BACKEND_DIR / ".env"

DEFAULT_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
DEFAULT_OPENAI_BASE = "https://api.openai.com/v1"

DEFAULT_GEMINI_MODELS = (
    "gemini-2.5-flash,gemini-2.0-flash,gemini-1.5-flash"
)
DEFAULT_OPENROUTER_MODEL = (
    "meta-llama/llama-3.2-11b-vision-instruct:free"
)
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


def _load_env_file() -> None:
    """Подхватить backend/.env, не перетирая уже заданные переменные."""

    if not ENV_FILE.is_file():
        return

    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for raw in lines:
        line = raw.strip()

        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[7:].strip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()

        if not key or key in os.environ:
            continue

        value = value.strip()

        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in "\"'"
        ):
            value = value[1:-1]

        os.environ[key] = value


_load_env_file()


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)

    if raw is None:
        return default

    return raw.strip().lower() not in {
        "",
        "0",
        "false",
        "no",
        "off",
    }


def _int_env(name: str, default: int) -> int:
    try:
        return max(5, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _normalized_provider() -> str:
    provider = (os.getenv("AI_API_PROVIDER") or "gemini").strip().lower()

    aliases = {
        "google": "gemini",
        "google-gemini": "gemini",
        "openai-compatible": "openrouter",
        "or": "openrouter",
    }

    return aliases.get(provider, provider)


def _provider_key(provider: str) -> str:
    if provider == "gemini":
        return (
            os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
            or ""
        )

    if provider == "openrouter":
        return os.getenv("OPENROUTER_API_KEY") or ""

    if provider == "openai":
        return os.getenv("OPENAI_API_KEY") or ""

    return ""


def _default_base(provider: str) -> str:
    if provider == "openrouter":
        return DEFAULT_OPENROUTER_BASE

    if provider == "openai":
        return DEFAULT_OPENAI_BASE

    return DEFAULT_GEMINI_BASE


def _default_models(provider: str) -> str:
    if provider == "openrouter":
        return DEFAULT_OPENROUTER_MODEL

    if provider == "openai":
        return DEFAULT_OPENAI_MODEL

    return DEFAULT_GEMINI_MODELS


def get_settings() -> dict:
    """Текущие настройки. Читаются при каждом вызове."""

    provider = _normalized_provider()

    models = [
        item.strip()
        for item in (
            os.getenv("AI_API_MODEL")
            or _default_models(provider)
        ).split(",")
        if item.strip()
    ]

    return {
        "provider": provider,
        "api_key": (
            os.getenv("AI_API_KEY")
            or _provider_key(provider)
        ).strip(),
        "models": models,
        "model": models[0] if models else "",
        "base_url": (
            os.getenv("AI_API_BASE_URL")
            or _default_base(provider)
        ).rstrip("/"),
        "timeout": _int_env("AI_API_TIMEOUT", 60),
        "web_search": _bool_env(
            "AI_ENABLE_WEB_SEARCH",
            provider == "gemini",
        ),
    }
