"""Единая точка работы с файлами задания.

Раскладка описана в app/config.py. Все стадии pipeline и server.py
должны ходить через этот сервис, а не собирать пути руками.

Правило: любые пути, которые попадают в stages[...]["result"],
хранятся относительно `folder` (корня задания). Так их уже резолвят
server.get_artifact (folder / artifact_path) и pipeline
(video = storage.resolve(prepared["preview"])). Для этого в сервисе
есть метод `relative(absolute)`.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any
from uuid import UUID

from app import config


class StorageService:
    """Файловые операции задания.

    - run_id=None  → только job-level операции (server.py).
    - run_id=<id>  → доступны также операции над runs/<run_id>/ (pipeline, stages).
    """

    def __init__(self, folder: Path | str, run_id: str | None = None) -> None:
        self.folder = Path(folder).resolve()
        self.run_id = run_id
        self._run_dir = (
            self.folder / config.RUNS_SUBDIR / run_id if run_id else None
        )

    # ─────────────── фабрики ───────────────

    @classmethod
    def for_job(cls, job_id: str) -> "StorageService":
        try:
            normalized = UUID(job_id).hex
        except (ValueError, TypeError):
            raise ValueError(f"invalid job_id: {job_id!r}") from None
        return cls(config.DATA_DIR / normalized)

    @classmethod
    def for_run(cls, job_id: str, run_id: str) -> "StorageService":
        return cls(cls.for_job(job_id).folder, run_id=run_id)

    # ─────────────── job-level свойства ───────────────

    @property
    def job_json(self) -> Path:
        return self.folder / config.JOB_FILENAME

    @property
    def source_file(self) -> Path:
        return self.folder / config.SOURCE_FILENAME

    @property
    def report_file(self) -> Path:
        return self.folder / config.REPORT_FILENAME

    @property
    def runs_root(self) -> Path:
        return self.folder / config.RUNS_SUBDIR

    @property
    def prepared_dir(self) -> Path:
        return self.folder / config.PREPARED_SUBDIR

    @property
    def result_dir(self) -> Path:
        return self.folder / config.RESULT_SUBDIR

    @property
    def run_dir(self) -> Path:
        if self._run_dir is None:
            raise RuntimeError("StorageService: run_id is not set")
        return self._run_dir

    @property
    def has_run(self) -> bool:
        return self._run_dir is not None

    # ─────────────── подготовка папок ───────────────

    def ensure_dirs(self) -> None:
        """Создать папки уровня задания (+ runs/<run_id>/, если задан)."""
        for d in (
            self.folder,
            self.runs_root,
            self.prepared_dir,
            self.result_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

        if self.has_run:
            self.run_dir.mkdir(parents=True, exist_ok=True)

    def ensure_run_dir(self) -> Path:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        return self.run_dir

    # ─────────────── безопасные пути ───────────────

    def resolve(self, relative: str | Path) -> Path:
        """Относительный путь от folder → абсолютный. Защита от `..`."""
        p = (self.folder / relative).resolve()
        if not p.is_relative_to(self.folder):
            raise ValueError(f"path escapes job folder: {relative}")
        return p

    def relative(self, absolute: Path | str) -> str:
        """Абсолютный путь → строка относительно folder.

        Именно такое значение кладётся в stages[...]["result"].
        """
        return str(Path(absolute).resolve().relative_to(self.folder))

    def resolve_in_runs(self, relative: str | Path) -> Path:
        """Путь для get_artifact: строго внутри runs/, иначе ValueError."""
        p = (self.folder / relative).resolve()
        if not p.is_relative_to(self.runs_root):
            raise ValueError(f"path escapes runs: {relative}")
        return p

    # ─────────────── run-level: запись ───────────────

    def run_path(self, name: str) -> Path:
        p = self.run_dir / name
        if not p.resolve().is_relative_to(self.run_dir.resolve()):
            raise ValueError(f"path escapes run dir: {name}")
        return p

    def save_bytes(self, name: str, data: bytes) -> Path:
        p = self.run_path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def save_text(self, name: str, text: str) -> Path:
        p = self.run_path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def save_json(self, name: str, obj: Any) -> Path:
        return self.save_text(
            name,
            json.dumps(obj, ensure_ascii=False, indent=2),
        )

    def save_file(self, name: str, src: str | Path) -> Path:
        """Скопировать готовый файл (кадр, аудио и т.п.) в runs/<id>."""
        p = self.run_path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, p)
        return p

    # ─────────────── run-level: чтение ───────────────

    def read_bytes(self, name: str) -> bytes:
        return self.run_path(name).read_bytes()

    def read_text(self, name: str) -> str:
        return self.run_path(name).read_text(encoding="utf-8")

    def read_json(self, name: str) -> Any:
        return json.loads(self.read_text(name))

    def run_exists(self, name: str) -> bool:
        return self.run_path(name).is_file()

    def list_run_files(self) -> list[Path]:
        if not self.run_dir.exists():
            return []
        return sorted(p for p in self.run_dir.rglob("*") if p.is_file())

    # ─────────────── job-level: запись ───────────────

    def open_source_for_write(self):
        """Streaming-запись исходника (server.py в create_job)."""
        self.folder.mkdir(parents=True, exist_ok=True)
        return self.source_file.open("wb")

    def save_source(self, src: str | Path) -> Path:
        """Готовый файл → original.bin (например, из тестов)."""
        self.folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, self.source_file)
        return self.source_file

    def save_result(self, obj: Any) -> Path:
        """Финальный результат (координаты) → result/coordinates.json."""
        self.result_dir.mkdir(parents=True, exist_ok=True)
        dst = self.result_dir / config.RESULT_FILENAME
        dst.write_text(
            json.dumps(obj, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return dst

    def read_result(self) -> Any:
        return json.loads(
            (self.result_dir / config.RESULT_FILENAME).read_text(encoding="utf-8")
        )

    def save_report(self, text: str) -> Path:
        """Атомарная запись report.md — как сейчас в server.py."""
        self.folder.mkdir(parents=True, exist_ok=True)
        target = self.report_file
        temporary = target.with_name(
            f"{target.name}.{os.getpid()}.{time.monotonic_ns()}.tmp"
        )
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, target)
        return target

    # ─────────────── очистка ───────────────

    def delete_run(self) -> None:
        if self.has_run and self._run_dir.exists():
            shutil.rmtree(self._run_dir)

    def delete_job(self) -> None:
        if self.folder.exists():
            shutil.rmtree(self.folder)