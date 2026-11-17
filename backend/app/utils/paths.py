"""Пути внутри папки задания.

relative() превращает абсолютный путь в относительный, чтобы
в job.json и отчёте хранились переносимые ссылки на артефакты.
"""

from pathlib import Path


def relative(folder: Path, path: Path) -> str:
    return path.relative_to(folder).as_posix()
