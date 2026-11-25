"""Семантические звуковые события через YAMNet (ONNX).

YAMNet — классификатор AudioSet на 521 класс. Для геолокации
интересны только звуки-улики: транспорт, сирены, колокола, вода,
животные, стройка, тип окружения. Поэтому в модуле хранится
курируемая таблица классов, а не все 521 подпись.

Модель не входит в репозиторий: ожидается файл
app/models/yamnet.onnx (16 кГц, моно). Если файла или
onnxruntime нет, model_available() возвращает False, а стадия
audio_structure аккуратно пропускает семантическую часть.

Классы AudioSet и их индексы — официальная карта YAMNet:
https://github.com/tensorflow/models/blob/master/research/audioset/yamnet/yamnet_class_map.csv
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np


SAMPLE_RATE = 16000
WINDOW_SECONDS = 0.96
HOP_SECONDS = 0.48

MIN_CONFIDENCE = 0.25
TOP_K = 3

DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parents[2] / "models" / "yamnet.onnx"
)

MODEL_PATH = Path(
    os.environ.get("VIDEO_SERVICE_YAMNET", DEFAULT_MODEL_PATH)
)


# index -> (имя класса AudioSet, русская подпись, важность)
#
# Важность — насколько звук помогает определить место:
# высокая  — почти однозначная улика (поезд, метро, колокол, море);
# средняя  — сужает тип места (толпа, стройка, трафик);
# низкая   — общий фон, почти не помогает.
CLASS_LABELS: dict[int, tuple[str, str, str]] = {
    # люди и толпа
    63: ("Chatter", "людные разговоры", "низкая"),
    64: ("Crowd", "толпа", "средняя"),
    65: ("Hubbub, speech noise, speech babble", "шумная толпа", "средняя"),
    66: ("Children playing", "играющие дети", "низкая"),
    # домашние и сельские животные
    69: ("Dog", "собака", "низкая"),
    76: ("Cat", "кошка", "низкая"),
    82: ("Horse", "лошадь", "средняя"),
    83: ("Clip-clop", "цокот копыт", "средняя"),
    85: ("Cattle, bovinae", "крупный рогатый скот", "средняя"),
    86: ("Moo", "мычание коровы", "средняя"),
    87: ("Cowbell", "коровьи бубенцы", "средняя"),
    90: ("Goat", "коза", "средняя"),
    92: ("Sheep", "овца", "средняя"),
    94: ("Chicken, rooster", "куры, петух", "средняя"),
    96: ("Crowing, cock-a-doodle-doo", "петух", "средняя"),
    99: ("Duck", "утка", "низкая"),
    101: ("Goose", "гусь", "низкая"),
    104: ("Roaring cats (lions, tigers)", "хищные кошки", "низкая"),
    106: ("Bird", "птицы", "низкая"),
    107: ("Bird vocalization, bird call, bird song", "пение птиц", "низкая"),
    110: ("Pigeon, dove", "голуби", "низкая"),
    112: ("Crow", "ворона", "низкая"),
    114: ("Owl", "сова", "средняя"),
    122: ("Cricket", "сверчки", "средняя"),
    127: ("Frog", "лягушки", "средняя"),
    129: ("Snake", "змея", "низкая"),
    131: ("Whale vocalization", "киты", "высокая"),
    # природа и погода
    277: ("Wind", "ветер", "низкая"),
    280: ("Thunderstorm", "гроза", "низкая"),
    281: ("Thunder", "гром", "низкая"),
    282: ("Water", "вода", "средняя"),
    283: ("Rain", "дождь", "низкая"),
    286: ("Stream", "ручей", "средняя"),
    287: ("Waterfall", "водопад", "высокая"),
    288: ("Ocean", "океан", "высокая"),
    289: ("Waves, surf", "прибой", "высокая"),
    # транспорт
    294: ("Vehicle", "транспорт", "низкая"),
    295: ("Boat, Water vehicle", "лодка", "высокая"),
    296: ("Sailboat, sailing ship", "парусник", "высокая"),
    298: ("Motorboat, speedboat", "моторная лодка", "высокая"),
    299: ("Ship", "судно", "высокая"),
    300: ("Motor vehicle (road)", "автотранспорт", "низкая"),
    301: ("Car", "автомобиль", "низкая"),
    302: ("Vehicle horn, car horn, honking", "сигнал автомобиля", "средняя"),
    308: ("Car passing by", "проезжающий автомобиль", "низкая"),
    310: ("Truck", "грузовик", "средняя"),
    315: ("Bus", "автобус", "средняя"),
    316: ("Emergency vehicle", "машина спецслужб", "высокая"),
    317: ("Police car (siren)", "полицейская сирена", "высокая"),
    318: ("Ambulance (siren)", "сирена скорой помощи", "высокая"),
    319: ("Fire engine, fire truck (siren)", "сирена пожарных", "высокая"),
    320: ("Motorcycle", "мотоцикл", "средняя"),
    321: ("Traffic noise, roadway noise", "шум трафика", "средняя"),
    322: ("Rail transport", "железнодорожный транспорт", "высокая"),
    323: ("Train", "поезд", "высокая"),
    324: ("Train whistle", "гудок поезда", "высокая"),
    325: ("Train horn", "гудок локомотива", "высокая"),
    326: ("Railroad car, train wagon", "железнодорожный вагон", "высокая"),
    327: ("Train wheels squealing", "скрип колёс поезда", "высокая"),
    328: ("Subway, metro, underground", "метро", "высокая"),
    329: ("Aircraft", "самолёт", "высокая"),
    330: ("Aircraft engine", "двигатель самолёта", "высокая"),
    331: ("Jet engine", "реактивный двигатель", "высокая"),
    333: ("Helicopter", "вертолёт", "высокая"),
    334: ("Fixed-wing aircraft, airplane", "самолёт", "высокая"),
    335: ("Bicycle", "велосипед", "низкая"),
    337: ("Engine", "двигатель", "низкая"),
    340: ("Lawn mower", "газонокосилка", "средняя"),
    341: ("Chainsaw", "бензопила", "средняя"),
    347: ("Accelerating, revving, vroom", "рёв двигателя", "низкая"),
    # городские объекты и тревоги
    349: ("Doorbell", "дверной звонок", "низкая"),
    382: ("Alarm", "тревога", "средняя"),
    390: ("Siren", "сирена", "высокая"),
    391: ("Civil defense siren", "сирена гражданской обороны", "высокая"),
    393: ("Smoke detector, smoke alarm", "пожарный извещатель", "низкая"),
    394: ("Fire alarm", "пожарная тревога", "средняя"),
    395: ("Foghorn", "туманный горн", "высокая"),
    396: ("Whistle", "свисток", "низкая"),
    397: ("Steam whistle", "паровой гудок", "средняя"),
    414: ("Jackhammer", "отбойный молоток", "средняя"),
    418: ("Power tool", "строительный инструмент", "средняя"),
    419: ("Drill", "дрель", "средняя"),
    420: ("Explosion", "взрыв", "средняя"),
    421: ("Gunshot, gunfire", "выстрелы", "средняя"),
    426: ("Fireworks", "фейерверк", "средняя"),
    427: ("Firecracker", "петарды", "средняя"),
    459: ("Basketball bounce", "баскетбольный мяч", "низкая"),
    # колокола и музыка
    25: ("Choir", "хор", "низкая"),
    26: ("Singing", "пение", "низкая"),
    27: ("Chant", "распев", "средняя"),
    28: ("Mantra", "мантра", "средняя"),
    132: ("Music", "музыка", "низкая"),
    195: ("Bell", "колокол", "средняя"),
    196: ("Church bell", "церковный колокол", "высокая"),
    197: ("Jingle bell", "бубенцы", "низкая"),
    198: ("Bicycle bell", "велозвонок", "низкая"),
    200: ("Chime", "перезвон", "низкая"),
    201: ("Wind chime", "ветряные колокольчики", "низкая"),
    202: ("Change ringing (campanology)", "церковные колокола", "высокая"),
    261: ("Song", "песня", "низкая"),
    # акустический контекст места
    494: ("Silence", "тишина", "низкая"),
    500: ("Inside, small room", "небольшое помещение", "низкая"),
    501: ("Inside, large room or hall", "большое помещение или зал", "средняя"),
    502: ("Inside, public space", "общественное помещение", "средняя"),
    503: ("Outside, urban or manmade", "улица, городская среда", "средняя"),
    504: ("Outside, rural or natural", "природа, сельская местность", "средняя"),
    508: ("Environmental noise", "окружающий шум", "низкая"),
}


def model_available() -> bool:
    """Есть ли модель YAMNet и onnxruntime."""

    if not MODEL_PATH.is_file():
        return False

    try:
        import onnxruntime  # noqa: F401

    except Exception:
        return False

    return True


def model_note() -> str:
    """Короткое пояснение для UI, почему звуки не распознаны."""

    if not MODEL_PATH.is_file():
        return (
            "Модель YAMNet не найдена (app/models/yamnet.onnx). "
            "Семантическое распознавание звуков пропущено."
        )

    return (
        "onnxruntime недоступен — семантическое распознавание "
        "звуков пропущено."
    )


class YamnetDetector:
    """Обёртка над ONNX-моделью YAMNet.

    analyze() режет waveform на перекрывающиеся окна 0.96 с с шагом
    0.48 с (родной вход YAMNet), берёт top-K классов выше порога и
    возвращает плоский список событий.
    """

    def __init__(
        self,
        model_path: Path | None = None,
        min_confidence: float = MIN_CONFIDENCE,
        top_k: int = TOP_K,
    ) -> None:
        import onnxruntime as ort

        path = Path(model_path or MODEL_PATH)

        if not path.is_file():
            raise FileNotFoundError(f"Нет модели YAMNet: {path}")

        self._session = ort.InferenceSession(
            str(path),
            providers=["CPUExecutionProvider"],
        )

        inputs = self._session.get_inputs()
        outputs = self._session.get_outputs()

        self._input_name = inputs[0].name
        self._input_rank = len(inputs[0].shape or [])

        self._score_output = _find_score_output(outputs)

        if self._score_output is None:
            raise ValueError(
                "В выходах YAMNet не найдена матрица классов."
            )

        self._min_confidence = float(min_confidence)
        self._top_k = max(1, int(top_k))

    def analyze(
        self,
        waveform: np.ndarray,
        sample_rate: int = SAMPLE_RATE,
    ) -> list[dict]:
        """Вернуть события [start, end, class_index, confidence, ...]."""

        samples = _prepare_waveform(waveform, sample_rate)

        if samples.size == 0:
            return []

        window = int(SAMPLE_RATE * WINDOW_SECONDS)
        hop = int(SAMPLE_RATE * HOP_SECONDS)

        events: list[dict] = []
        position = 0
        total = samples.size

        while position < total:
            chunk = samples[position:position + window]

            if chunk.size < window:
                chunk = np.pad(chunk, (0, window - chunk.size))

            scores = self._score(chunk)
            start = position / SAMPLE_RATE
            end = min(total, position + window) / SAMPLE_RATE

            for class_index, confidence in _top_classes(
                scores,
                self._top_k,
                self._min_confidence,
            ):
                label = CLASS_LABELS.get(class_index)

                if label is None:
                    continue

                kind, label_ru, importance = label

                events.append({
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "class_index": class_index,
                    "kind": kind,
                    "label_ru": label_ru,
                    "importance": importance,
                    "confidence": round(float(confidence), 4),
                })

            position += hop

        return events

    def _score(self, chunk: np.ndarray) -> np.ndarray:
        """Прогнать одно окно и вернуть средние scores по классам."""

        data = chunk.astype(np.float32)

        if self._input_rank >= 2:
            data = data.reshape(1, -1)

        outputs = self._session.run(
            [self._score_output],
            {self._input_name: data},
        )

        scores = np.asarray(outputs[0], dtype=np.float32)

        if scores.ndim == 1:
            return scores

        # YAMNet выдаёт scores по кадрам: [frames, classes].
        scores = scores.reshape(-1, scores.shape[-1])

        return scores.mean(axis=0)


def summarize(events: list[dict]) -> list[dict]:
    """Сгруппировать события по классу звука.

    Возвращает список сводок, отсортированный по важности и числу
    участков: kind, label_ru, importance, count, total_seconds,
    max_confidence, intervals [[start, end], ...].
    """

    grouped: dict[int, dict] = {}

    for event in events:
        class_index = int(event.get("class_index", -1))
        start = float(event.get("start", 0.0))
        end = float(event.get("end", start))
        confidence = float(event.get("confidence", 0.0))

        item = grouped.get(class_index)

        if item is None:
            item = {
                "kind": event.get("kind"),
                "label_ru": event.get("label_ru"),
                "importance": event.get("importance", "низкая"),
                "count": 0,
                "total_seconds": 0.0,
                "max_confidence": 0.0,
                "intervals": [],
            }
            grouped[class_index] = item

        item["count"] += 1
        item["total_seconds"] += max(0.0, end - start)
        item["max_confidence"] = max(item["max_confidence"], confidence)
        item["intervals"].append([round(start, 3), round(end, 3)])

    summaries = []

    for item in grouped.values():
        item["total_seconds"] = round(item["total_seconds"], 2)
        item["max_confidence"] = round(item["max_confidence"], 4)
        item["intervals"] = _merge_intervals(item["intervals"])
        summaries.append(item)

    importance_rank = {"высокая": 0, "средняя": 1, "низкая": 2}

    summaries.sort(
        key=lambda item: (
            importance_rank.get(item["importance"], 3),
            -item["count"],
            -item["max_confidence"],
        )
    )

    return summaries


def _merge_intervals(
    intervals: list[list[float]],
    gap: float = 0.6,
) -> list[list[float]]:
    """Склеить соседние окна одного звука в участки."""

    if not intervals:
        return []

    ordered = sorted(intervals, key=lambda pair: pair[0])
    merged = [list(ordered[0])]

    for start, end in ordered[1:]:
        last = merged[-1]

        if start <= last[1] + gap:
            last[1] = max(last[1], end)

        else:
            merged.append([start, end])

    return merged


def _top_classes(
    scores: np.ndarray,
    top_k: int,
    min_confidence: float,
) -> list[tuple[int, float]]:
    """Индексы top-K классов выше порога."""

    if scores.size == 0:
        return []

    count = min(top_k, scores.size)
    indices = np.argpartition(-scores, count - 1)[:count]
    indices = indices[np.argsort(-scores[indices])]

    result = []

    for index in indices:
        confidence = float(scores[int(index)])

        if confidence < min_confidence:
            continue

        result.append((int(index), confidence))

    return result


def _prepare_waveform(
    waveform: np.ndarray,
    sample_rate: int,
) -> np.ndarray:
    """Привести сигнал к моно 16 кГц float32."""

    samples = np.asarray(waveform, dtype=np.float32).reshape(-1)

    if samples.size == 0:
        return samples

    if sample_rate != SAMPLE_RATE and sample_rate > 0:
        target = max(
            1,
            int(round(samples.size * SAMPLE_RATE / sample_rate)),
        )
        source_axis = np.linspace(0.0, 1.0, samples.size, endpoint=False)
        target_axis = np.linspace(0.0, 1.0, target, endpoint=False)
        samples = np.interp(target_axis, source_axis, samples).astype(
            np.float32,
        )

    peak = float(np.max(np.abs(samples))) if samples.size else 0.0

    if peak > 1.0:
        samples = samples / peak

    return samples


def _find_score_output(outputs) -> str | None:
    """Найти выход со scores: последняя размерность — 521 класс."""

    fallback = None

    for output in outputs:
        shape = output.shape or []
        last = shape[-1] if shape else None

        if isinstance(last, int) and last == 521:
            return output.name

        if fallback is None:
            fallback = output.name

    return fallback
