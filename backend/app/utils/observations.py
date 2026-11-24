"""Создание наблюдений.

Функция observation() принимает поля, проверяет их через модель
Observation и возвращает обычный словарь для сохранения в job.json.
Так все этапы создают записи одинаковой структуры.
"""

from app.models.models import Observation


def observation(**kwargs) -> dict:
    return Observation(**kwargs).model_dump()
