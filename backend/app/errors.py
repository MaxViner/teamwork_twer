"""Исключения сервиса.

SkipStage — этап штатно пропущен (например, в видео нет звука).
JobError — ошибка состояния или выполнения задания.
"""

class SkipStage(Exception):
    pass
class JobError(Exception):
    """Ошибка состояния или выполнения задания."""


class SkipStage(Exception):
    """Этап должен быть пропущен без пометки как failed."""