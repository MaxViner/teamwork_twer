"""Работа с русским текстом.

Простые помощники для конспекта, структуры видео и поиска:
разбиение на предложения, слова, отбрасывание служебных слов и
подсчёт ключевых терминов. Без внешних моделей и сети.
"""

import re
from collections import Counter


SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+")
WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9\-]*")


STOPWORDS = {
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как",
    "а", "то", "все", "всё", "она", "так", "его", "но", "да", "ты",
    "к", "у", "же", "вы", "за", "бы", "по", "только", "ее", "её",
    "мне", "было", "вот", "от", "меня", "еще", "ещё", "нет", "о",
    "об", "из", "ему", "теперь", "когда", "даже", "ну", "вдруг",
    "ли", "если", "уже", "или", "ни", "быть", "был", "была", "были",
    "него", "до", "вас", "нибудь", "опять", "уж", "вам", "ведь",
    "там", "потом", "себя", "ничего", "ей", "может", "они", "тут",
    "где", "есть", "надо", "ней", "для", "мы", "тебя", "их", "чем",
    "была", "сам", "чтоб", "без", "будто", "чего", "раз", "тоже",
    "себе", "под", "будет", "ж", "тогда", "кто", "этот", "того",
    "потому", "этого", "какой", "совсем", "ним", "здесь", "этом",
    "один", "почти", "мой", "тем", "чтобы", "нее", "неё", "сейчас",
    "были", "куда", "зачем", "всех", "никогда", "можно", "при",
    "наконец", "два", "об", "другой", "хоть", "после", "над", "больше",
    "тот", "через", "эти", "нас", "про", "всего", "них", "какая",
    "много", "разве", "три", "эту", "моя", "впрочем", "хорошо", "свою",
    "этой", "перед", "иногда", "лучше", "чуть", "том", "нельзя",
    "такой", "им", "более", "всегда", "конечно", "всю", "между",
    "the", "and", "for", "are", "but", "not", "you", "all", "any",
    "can", "had", "her", "was", "one", "our", "out", "day", "get",
    "has", "him", "his", "how", "its", "may", "new", "now", "old",
    "see", "two", "way", "who", "boy", "did", "she", "use", "her",
    "with", "have", "this", "will", "your", "from", "they", "know",
    "want", "been", "good", "much", "some", "time", "very", "when",
    "come", "here", "just", "like", "long", "make", "many", "more",
    "only", "over", "such", "take", "than", "them", "well", "were",
    "what", "with", "this", "that", "there", "their", "would", "about",
}


def sentences(text: str) -> list[str]:
    """Делит текст на предложения и убирает пустые."""
    result = []

    for part in SENTENCE_RE.split(str(text or "")):
        cleaned = " ".join(part.split()).strip()

        if cleaned:
            result.append(cleaned)

    return result


def words(text: str) -> list[str]:
    """Слова в нижнем регистре без служебных."""
    return [
        token.casefold()
        for token in WORD_RE.findall(str(text or ""))
        if len(token) >= 3
        and token.casefold() not in STOPWORDS
        and re.search(r"[A-Za-zА-Яа-яЁё]", token)
    ]


def keywords(text: str, limit: int = 12) -> list[dict]:
    """Частые содержательные слова с количеством."""
    counter = Counter(words(text))

    return [
        {"word": word, "count": count}
        for word, count in counter.most_common(limit)
    ]


def keyword_set(text: str, limit: int = 40) -> set[str]:
    return {
        item["word"]
        for item in keywords(text, limit)
    }


def normalize(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


def sentence_score(
    sentence: str,
    frequent: set[str],
) -> float:
    """Ценность предложения для конспекта."""
    tokens = words(sentence)

    if not tokens:
        return 0.0

    hits = sum(1 for token in tokens if token in frequent)
    length = len(tokens)

    # Слишком короткие и слишком длинные фразы менее полезны.
    length_factor = 1.0 if 5 <= length <= 28 else 0.55

    return hits / (length ** 0.65) * length_factor


def best_sentences(
    items: list[tuple[float, str]],
    frequent: set[str],
    limit: int = 8,
) -> list[dict]:
    """
    Ранжирует предложения с таймкодами.

    items — пары (секунды, текст).
    """
    scored = []

    for moment, text in items:
        for sentence in sentences(text):
            if len(words(sentence)) < 3:
                continue

            score = sentence_score(sentence, frequent)

            if score <= 0:
                continue

            scored.append({
                "start": round(float(moment), 3),
                "text": sentence,
                "score": round(score, 4),
            })

    scored.sort(
        key=lambda item: (-item["score"], item["start"])
    )

    picked = []
    seen = set()

    for item in scored:
        key = normalize(item["text"])[:80]

        if key in seen:
            continue

        seen.add(key)
        picked.append(item)

        if len(picked) >= limit:
            break

    picked.sort(key=lambda item: item["start"])

    return picked
