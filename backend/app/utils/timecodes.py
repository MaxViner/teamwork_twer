"""Таймкоды в удобном виде.

numeric_time превращает значение в неотрицательное число секунд,
timestamp форматирует его как ЧЧ:ММ:СС.мс. Функции терпимы к строкам
и пропускают некорректные значения.
"""

import math


def numeric_time(value) -> float | None:
    """Возвращает неотрицательные секунды или None."""
    try:
        number = float(value)

    except (TypeError, ValueError, OverflowError):
        return None

    if not math.isfinite(number) or number < 0:
        return None

    return number


def timestamp(value) -> str:
    """Форматирует секунды как ЧЧ:ММ:СС.мсс."""
    seconds = numeric_time(value)

    if seconds is None:
        return "не задано"

    milliseconds = round(seconds * 1000)

    hours, remainder = divmod(
        milliseconds,
        3_600_000,
    )
    minutes, remainder = divmod(
        remainder,
        60_000,
    )
    seconds, milliseconds = divmod(
        remainder,
        1000,
    )

    return (
        f"{hours:02d}:{minutes:02d}:"
        f"{seconds:02d}.{milliseconds:03d}"
    )
