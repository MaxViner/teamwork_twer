"""Короткие названия мест.

Достаёт из длинных фраз вроде «приехал в деревню, в Тирскую
область» компактное «Тирскую область». Нужно, чтобы отчёт и поиск
не показывали целые предложения вместо топонимов.
"""

import re

from app.text import normalize


PLACE_KEYWORD_RE = re.compile(
    r"^(?:област|обл\.|район|кра[йяю]|республик|деревн|посёл|"
    r"посел|сел[оа]|станиц|хутор|город|полуостров|озер|"
    r"рек[аиу]|гор[аыу]|хребет|залив|порт|станци|вокзал|"
    r"аэропорт|метро)",
    re.IGNORECASE,
)

REGION_KEYWORD_RE = re.compile(
    r"^(?:област|обл\.|район|кра[йяю]|республик)",
    re.IGNORECASE,
)

PLACE_STOPWORDS = {
    "вот", "там", "тут", "здесь", "эта", "это", "этот", "такая",
    "такой", "была", "был", "было", "были", "будет", "есть",
    "начинается", "заканчивается", "стоит", "видно", "видна",
    "и", "а", "но", "в", "во", "на", "из", "с", "со", "у", "к",
    "ко", "по", "о", "об", "от", "до", "за", "под", "над", "при",
    "для", "что", "как", "где", "когда", "тоже", "ещё", "еще",
    "уже", "очень", "почти", "через", "около", "возле", "рядом",
    "прямо", "сейчас", "потом", "тогда", "туда", "сюда", "назад",
    "вперёд", "вперед", "дальше", "ближе", "самая", "самый",
    "самое", "весь", "вся", "всё", "все", "один", "одна", "одно",
}

PLACE_ADJECTIVE_RE = re.compile(
    r"(?:ская|ской|скую|ский|ского|скому|ском|ая|ой|ую|ий|"
    r"ого|ому|им|ом|ые|ых|ым|ыми)$",
    re.IGNORECASE,
)

WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9\-]+")


def place_tokens(value) -> list[str]:
    """Все короткие топонимы, найденные в фразе."""
    tokens = WORD_RE.findall(str(value))
    found = []

    for index, token in enumerate(tokens):
        if not PLACE_KEYWORD_RE.match(token):
            continue

        previous = tokens[index - 1] if index > 0 else None

        if (
            previous
            and _looks_named(previous)
            and not PLACE_KEYWORD_RE.match(previous)
        ):
            found.append(f"{previous} {token}")

        following = (
            tokens[index + 1]
            if index + 1 < len(tokens)
            else None
        )

        if (
            following
            and following[:1].isupper()
            and following.casefold() not in PLACE_STOPWORDS
            and not PLACE_KEYWORD_RE.match(following)
        ):
            found.append(f"{token} {following}")

    result = []

    for item in found:
        cleaned = " ".join(item.split())
        key = normalize(cleaned)

        if key and key not in {
            normalize(existing) for existing in result
        }:
            result.append(cleaned)

    return result


def clean_place(value):
    """Одно самое конкретное название места или None."""
    found = place_tokens(value)

    if not found:
        return None

    found.sort(
        key=lambda item: (
            0 if REGION_KEYWORD_RE.match(item.split()[-1]) else 1,
            -len(item),
        )
    )

    best = found[0]

    if best[:1].islower():
        best = best[0].upper() + best[1:]

    return best


def _looks_named(token):
    if not token or token.casefold() in PLACE_STOPWORDS:
        return False

    if token[:1].isupper():
        return True

    return bool(PLACE_ADJECTIVE_RE.search(token))
