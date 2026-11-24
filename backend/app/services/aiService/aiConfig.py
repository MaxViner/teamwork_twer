"""Универсальная конфигурация AI-провайдера.

Провайдер, протокол, ключ, модели и base URL
задаются только через backend/.env.
В коде нет привязки к конкретному сервису.
"""


import os
from pathlib import Path



BACKEND_DIR = Path(__file__).resolve().parents[3]
ENV_FILE = BACKEND_DIR / ".env"



DEFAULT_TIMEOUT = 60



def _load_env_file() -> None:
    """Подхватить backend/.env, не перетирая переменные окружения."""


    if not ENV_FILE.is_file():
        return


    try:
        lines = ENV_FILE.read_text(
            encoding="utf-8",
        ).splitlines()


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



def _bool_env(
    name: str,
    default: bool,
) -> bool:
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



def _int_env(
    name: str,
    default: int,
) -> int:
    try:
        return max(
            5,
            int(
                os.getenv(
                    name,
                    str(default),
                )
            ),
        )


    except (TypeError, ValueError):
        return default



def _provider_key(provider: str) -> str:
    """Найти ключ по нескольким стандартным именам переменных."""


    upper = provider.upper().replace(
        "-",
        "_",
    )


    candidates = [
        f"{upper}_API_KEY",
        "AI_API_KEY",
        "ZVENO_API_KEY",
        "OPENROUTER_API_KEY",
        "PLNEX_API_KEY",
        "OPENAI_API_KEY",
    ]


    for name in candidates:
        value = os.getenv(name)


        if value and value.strip():
            return value.strip()


    return ""



def _provider_base_url(provider: str) -> str:
    """Найти base URL по нескольким стандартным именам переменных."""


    upper = provider.upper().replace(
        "-",
        "_",
    )


    candidates = [
        f"{upper}_BASE_URL",
        "AI_API_BASE_URL",
        "OPENAI_BASE_URL",
    ]


    for name in candidates:
        value = os.getenv(name)


        if value and value.strip():
            return value.strip().rstrip("/")


    return "https://api.openai.com/v1"



def get_settings() -> dict:
    """Текущие настройки. Читаются при каждом вызове."""


    provider = (
        os.getenv("AI_API_PROVIDER")
        or "openai"
    ).strip().lower()


    protocol = (
        os.getenv("AI_API_PROTOCOL")
        or "openai"
    ).strip().lower()


    if protocol not in {
        "openai",
        "anthropic",
    }:
        protocol = "openai"


    raw_models = (
        os.getenv("AI_API_MODEL")
        or ""
    )


    models = [
        item.strip()
        for item in raw_models.split(",")
        if item.strip()
    ]


    default_model = (
        models[0]
        if models
        else ""
    )


    chat_model = (
        os.getenv("AI_CHAT_MODEL")
        or default_model
    ).strip()


    vision_model = (
        os.getenv("AI_VISION_MODEL")
        or default_model
    ).strip()


    return {
        "provider": provider,
        "protocol": protocol,
        "api_key": _provider_key(provider),
        "models": models,
        "model": default_model,
        "chat_model": chat_model,
        "vision_model": vision_model,
        "base_url": _provider_base_url(provider),
        "timeout": _int_env(
            "AI_API_TIMEOUT",
            DEFAULT_TIMEOUT,
        ),
        "web_search": False,
    }