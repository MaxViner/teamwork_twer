"""Контрольная сумма файла.

sha256_of() читает файл блоками по 1 МБ и считает SHA-256,
не загружая видео целиком в память. Хэш сохраняется в задании,
чтобы отличать одинаковые загрузки.
"""

import hashlib
from pathlib import Path


def sha256_of(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)

    return digest.hexdigest()
