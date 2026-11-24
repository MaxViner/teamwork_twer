"""Точка входа backend-сервера.

Запускает FastAPI-приложение через uvicorn на 127.0.0.1:8000.
Использование: python -m app.main.
"""

import uvicorn

from .APIGateway.server import appServer


def main() -> None:
    uvicorn.run(
        "app.APIGateway.server:appServer",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()