"""Запуск внешних программ.

command() запускает процесс, ограничивает время выполнения и
возвращает stdout, а при ошибке показывает stderr.
require_tools() проверяет, что нужные программы есть в PATH.
"""

import shutil
import subprocess
from pathlib import Path


def command(args: list[str], timeout: int = 1800) -> str:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"Превышено время выполнения: {Path(args[0]).name}"
        ) from None

    if result.returncode:
        raise RuntimeError(
            f"{Path(args[0]).name}: {result.stderr[-2500:]}"
        )

    return result.stdout


def require_tools(*names: str) -> None:
    missing = [name for name in names if not shutil.which(name)]

    if missing:
        raise RuntimeError(
            f"Не найдены инструменты в PATH: {', '.join(missing)}."
        )
