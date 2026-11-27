"""Слабые гео-улики: фенология, птицы, стек кадров, агрегация.

Пакет не зависит от основного пайплайна и не делает сетевых
запросов. Стадии вызывают его функции, чтобы добавить независимые
каналы улик и заменить средний confidence на лог-правдоподобие.
"""

from app.services.weakCluesService.service import (
    aggregate,
    collect_weak_clues,
    readiness,
)

__all__ = [
    "aggregate",
    "collect_weak_clues",
    "readiness",
]
