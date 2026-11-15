from pathlib import Path


def relative(folder: Path, path: Path) -> str:
    return path.relative_to(folder).as_posix()
