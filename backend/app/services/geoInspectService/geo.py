"""Извлечение и объединение географических признаков.

Модуль не выполняет геокодирование и не обращается к картам.
Он собирает независимые сигналы (GPS, адреса, телефоны, домены,
бренды, язык, валюту, визуальный профиль), оценивает их и
формирует проверяемое «локационное досье» с поисковыми запросами.
"""

import re
from collections import Counter


COORDINATES_PATTERN = re.compile(
    r"(-?\d{1,2}[.,]\d{3,})[,\s;]+"
    r"(-?\d{1,3}[.,]\d{3,})"
)


ADDRESS_PATTERN = re.compile(
    r"\b(?:ул\.?|улиц\w*|проспект\w*|пр-т|пр\.|"
    r"переул\w*|шоссе|набережн\w*|бульвар\w*|б-р|"
    r"площад\w*|пл\.|проезд\w*|тупик\w*|микрорайон\w*|"
    r"мкр\.?|квартал\w*|кв-л|"
    r"street|road|avenue|square)\s+"
    r"[«\"']?[A-ZА-ЯЁ][\w\-\.]*(?:\s+[A-ZА-ЯЁ][\w\-\.]*){0,3}"
    r"(?:[,\s]+(?:д\.?\s*)?\d+[A-Za-zА-Яа-я]?)?",
    re.IGNORECASE | re.UNICODE,
)


POSTAL_PATTERN = re.compile(r"\b\d{6}\b")


URL_PATTERN = re.compile(
    r"(?:https?://|www\.)[^\s\"'<>]+",
    re.IGNORECASE,
)


BARE_DOMAIN_PATTERN = re.compile(
    r"\b[a-z0-9][a-z0-9\-]{1,62}\.(?:ru|by|kz|ua|uz|kg|"
    r"am|ge|az|md|com|net|org|io|me|travel|shop|site|"
    r"online|de|fr|it|es|pl|tr|cn|jp|kr|in|ae|il|"
    r"uk|us|ca|fi|se|no|dk|cz|sk|hu|ro|bg|rs|hr|"
    r"si|gr|pt|nl|be|ch|at|ie|is|au|nz|br|mx|ar|"
    r"cl|za|eg|th|vn|id|my|sg|ph)\b",
    re.IGNORECASE,
)


PHONE_PATTERN = re.compile(
    r"(?:\+?\d[\d\s\-()]{8,18}\d)"
)


LICENSE_PLATE_PATTERNS = (
    (
        "RU",
        re.compile(
            r"\b[АВЕКМНОРСТУХ]\s?\d{3}\s?"
            r"[АВЕКМНОРСТУХ]{2}\s?\d{2,3}\b"
        ),
    ),
    (
        "BY",
        re.compile(r"\b\d{4}\s?[A-ZА-Я]{2}-?\d\b"),
    ),
)


CURRENCY_PATTERNS = (
    ("RU", re.compile(r"₽|\bруб(?:лей|ля|ль|\.)?\b", re.I)),
    ("KZ", re.compile(r"₸|\bтенге\b", re.I)),
    ("UA", re.compile(r"₴|\bгрн\b|\bгривен\b", re.I)),
    ("BY", re.compile(r"\bBYN\b|\bбел\.?\s?руб", re.I)),
    ("EU", re.compile(r"€|\bEUR\b", re.I)),
    ("US", re.compile(r"\$|\bUSD\b", re.I)),
    ("GB", re.compile(r"£|\bGBP\b", re.I)),
    ("TR", re.compile(r"₺|\bTRY\b", re.I)),
    ("IN", re.compile(r"₹|\bINR\b", re.I)),
)


TRANSPORT_PATTERN = re.compile(
    r"\b(?:маршрут(?:ка)?|автобус|троллейбус|трамвай|"
    r"электричка|метро|станция|вокзал|аэропорт|порт|"
    r"причал|паром)\b[^.!?\n]{0,40}",
    re.IGNORECASE,
)


UNIT_PATTERN = re.compile(
    r"(?:\b\d+[.,]?\d*\s?(?:км/ч|м/с|°C|°F|кг|км|м|см)\b)"
)


PLACE_KEYWORDS = (
    "город",
    "городе",
    "городок",
    "район",
    "районе",
    "область",
    "области",
    "край",
    "крае",
    "республика",
    "республике",
    "посёлок",
    "поселок",
    "село",
    "деревня",
    "станица",
    "хутор",
    "метро",
    "вокзал",
    "аэропорт",
    "порт",
    "станция",
    "полуостров",
    "залив",
    "озеро",
    "река",
    "гора",
    "хребет",
    "заповедник",
    "национальный парк",
)


PLACE_PATTERN = re.compile(
    r"\b(?:г\.|гор\.|город\w*|посёл\w*|посел\w*|сел[оа]|"
    r"деревн\w*|станиц\w*|хутор\w*|район\w*|област\w*|"
    r"кра[йяю]|республик\w*)\s+"
    r"[«\"']?([A-ZА-ЯЁ][\w\-]+(?:\s+[A-ZА-ЯЁ][\w\-]+){0,2})",
    re.UNICODE,
)


BRANDS = {
    "пятёрочка": ("RU", "сеть магазинов"),
    "пятерочка": ("RU", "сеть магазинов"),
    "магнит": ("RU", "сеть магазинов"),
    "перекрёсток": ("RU", "сеть магазинов"),
    "перекресток": ("RU", "сеть магазинов"),
    "вкусвилл": ("RU", "сеть магазинов"),
    "ашан": ("RU", "сеть магазинов"),
    "лента": ("RU", "сеть магазинов"),
    "победа": ("RU", "сеть магазинов"),
    "wildberries": ("RU", "маркетплейс"),
    "ozon": ("RU", "маркетплейс"),
    "яндекс": ("RU", "сервис"),
    "сбербанк": ("RU", "банк"),
    "сбер": ("RU", "банк"),
    "тинькофф": ("RU", "банк"),
    "альфа-банк": ("RU", "банк"),
    "втб": ("RU", "банк"),
    "роснефть": ("RU", "АЗС"),
    "лукойл": ("RU", "АЗС"),
    "газпромнефть": ("RU", "АЗС"),
    "тебойл": ("RU", "АЗС"),
    "мтс": ("RU", "связь"),
    "мегафон": ("RU", "связь"),
    "билайн": ("RU", "связь"),
    "теле2": ("RU", "связь"),
    "почта россии": ("RU", "почта"),
    "ржд": ("RU", "транспорт"),
    "аэрофлот": ("RU", "авиакомпания"),
    "kaspi": ("KZ", "банк"),
    "халык": ("KZ", "банк"),
    "halyk": ("KZ", "банк"),
    "jusan": ("KZ", "банк"),
    "magnum": ("KZ", "сеть магазинов"),
    "kcell": ("KZ", "связь"),
    "activ": ("KZ", "связь"),
    "беларусбанк": ("BY", "банк"),
    "евроопт": ("BY", "сеть магазинов"),
    "белтелеком": ("BY", "связь"),
    "приватбанк": ("UA", "банк"),
    "київстар": ("UA", "связь"),
    "kyivstar": ("UA", "связь"),
    "rozetka": ("UA", "маркетплейс"),
    "нова пошта": ("UA", "доставка"),
    "новая почта": ("UA", "доставка"),
    "apple": ("US", "техника"),
    "samsung": ("KR", "техника"),
    "xiaomi": ("CN", "техника"),
    "huawei": ("CN", "техника"),
    "gopro": ("US", "камера"),
    "dji": ("CN", "дрон"),
    "canon": ("JP", "камера"),
    "nikon": ("JP", "камера"),
    "sony": ("JP", "техника"),
}


LEGAL_FORMS = (
    ("RU", re.compile(r"\b(?:ООО|ОАО|ЗАО|ПАО|АО|ИП)\b")),
    ("KZ", re.compile(r"\bТОО\b")),
    ("BY", re.compile(r"\b(?:ЧУП|ОДО|УП)\b")),
)


TLD_COUNTRIES = {
    "ru": "RU",
    "by": "BY",
    "kz": "KZ",
    "ua": "UA",
    "uz": "UZ",
    "kg": "KG",
    "am": "AM",
    "ge": "GE",
    "az": "AZ",
    "md": "MD",
    "de": "DE",
    "fr": "FR",
    "it": "IT",
    "es": "ES",
    "pl": "PL",
    "tr": "TR",
    "cn": "CN",
    "jp": "JP",
    "kr": "KR",
    "in": "IN",
    "ae": "AE",
    "il": "IL",
    "uk": "GB",
    "us": "US",
    "ca": "CA",
    "fi": "FI",
    "se": "SE",
    "no": "NO",
    "dk": "DK",
    "cz": "CZ",
    "sk": "SK",
    "hu": "HU",
    "ro": "RO",
    "bg": "BG",
    "rs": "RS",
    "hr": "HR",
    "si": "SI",
    "gr": "GR",
    "pt": "PT",
    "nl": "NL",
    "be": "BE",
    "ch": "CH",
    "at": "AT",
    "ie": "IE",
    "is": "IS",
    "au": "AU",
    "nz": "NZ",
    "br": "BR",
    "mx": "MX",
    "ar": "AR",
    "cl": "CL",
    "za": "ZA",
    "eg": "EG",
    "th": "TH",
    "vn": "VN",
    "id": "ID",
    "my": "MY",
    "sg": "SG",
    "ph": "PH",
}


COUNTRY_NAMES = {
    "RU": "Россия",
    "BY": "Беларусь",
    "KZ": "Казахстан",
    "UA": "Украина",
    "UZ": "Узбекистан",
    "KG": "Кыргызстан",
    "AM": "Армения",
    "GE": "Грузия",
    "AZ": "Азербайджан",
    "MD": "Молдова",
    "US": "США",
    "GB": "Великобритания",
    "DE": "Германия",
    "FR": "Франция",
    "IT": "Италия",
    "ES": "Испания",
    "PL": "Польша",
    "TR": "Турция",
    "CN": "Китай",
    "JP": "Япония",
    "KR": "Южная Корея",
    "IN": "Индия",
    "BR": "Бразилия",
    "EU": "Евросоюз",
    "AE": "ОАЭ",
    "IL": "Израиль",
    "CA": "Канада",
    "FI": "Финляндия",
    "SE": "Швеция",
    "NO": "Норвегия",
    "DK": "Дания",
    "CZ": "Чехия",
    "SK": "Словакия",
    "HU": "Венгрия",
    "RO": "Румыния",
    "BG": "Болгария",
    "RS": "Сербия",
    "HR": "Хорватия",
    "SI": "Словения",
    "GR": "Греция",
    "PT": "Португалия",
    "NL": "Нидерланды",
    "BE": "Бельгия",
    "CH": "Швейцария",
    "AT": "Австрия",
    "IE": "Ирландия",
    "IS": "Исландия",
    "AU": "Австралия",
    "NZ": "Новая Зеландия",
    "MX": "Мексика",
    "AR": "Аргентина",
    "CL": "Чили",
    "ZA": "ЮАР",
    "EG": "Египет",
    "TH": "Таиланд",
    "VN": "Вьетнам",
    "ID": "Индонезия",
    "MY": "Малайзия",
    "SG": "Сингапур",
    "PH": "Филиппины",
}


DEVICE_COUNTRIES = {
    "apple": "US",
    "iphone": "US",
    "samsung": "KR",
    "xiaomi": "CN",
    "redmi": "CN",
    "huawei": "CN",
    "honor": "CN",
    "oneplus": "CN",
    "oppo": "CN",
    "vivo": "CN",
    "gopro": "US",
    "dji": "CN",
    "canon": "JP",
    "nikon": "JP",
    "sony": "JP",
    "panasonic": "JP",
    "garmin": "US",
}


PHONE_PREFIXES = (
    ("375", "BY"),
    ("380", "UA"),
    ("998", "UZ"),
    ("996", "KG"),
    ("374", "AM"),
    ("995", "GE"),
    ("994", "AZ"),
    ("373", "MD"),
    ("48", "PL"),
    ("49", "DE"),
    ("33", "FR"),
    ("39", "IT"),
    ("34", "ES"),
    ("44", "GB"),
    ("90", "TR"),
    ("86", "CN"),
    ("81", "JP"),
    ("82", "KR"),
    ("91", "IN"),
    ("55", "BR"),
    ("52", "MX"),
    ("54", "AR"),
    ("56", "CL"),
    ("27", "ZA"),
    ("20", "EG"),
    ("66", "TH"),
    ("84", "VN"),
    ("62", "ID"),
    ("60", "MY"),
    ("65", "SG"),
    ("63", "PH"),
    ("971", "AE"),
    ("972", "IL"),
    ("7", "RU"),
    ("1", "US"),
)


CYRILLIC_PATTERN = re.compile(r"[А-Яа-яЁё]")
LATIN_PATTERN = re.compile(r"[A-Za-z]")


SPECIAL_SCRIPTS = {
    "KZ": set("әғқңөұүһ"),
    "BY": set("ў"),
    "UA": set("іїєґ"),
}


def extract_text_evidence(
    text: str,
    origin: str,
) -> list[dict]:
    text = str(text or "").strip()

    if not text:
        return []

    evidence = []
    lowered = text.casefold()

    for match in COORDINATES_PATTERN.finditer(text):
        try:
            latitude = float(
                match.group(1).replace(",", ".")
            )
            longitude = float(
                match.group(2).replace(",", ".")
            )

        except ValueError:
            continue

        if not (
            -90 <= latitude <= 90
            and -180 <= longitude <= 180
        ):
            continue

        evidence.append({
            "kind": "coordinates",
            "label": "Координаты в тексте",
            "text": f"{latitude:.6f}, {longitude:.6f}",
            "confidence": 0.85,
            "country_hints": {},
            "details": {
                "latitude": latitude,
                "longitude": longitude,
                "origin": origin,
            },
        })

    for match in ADDRESS_PATTERN.finditer(text):
        value = " ".join(match.group(0).split())

        if len(value) < 6:
            continue

        evidence.append({
            "kind": "address",
            "label": "Возможный адрес",
            "text": value,
            "confidence": 0.6,
            "country_hints": {},
            "details": {
                "origin": origin,
                "place": value,
            },
        })

    for match in PLACE_PATTERN.finditer(text):
        value = " ".join(match.group(0).split())

        if len(value) < 6:
            continue

        evidence.append({
            "kind": "place_mention",
            "label": "Возможное упоминание места",
            "text": value,
            "confidence": 0.45,
            "country_hints": {},
            "details": {
                "origin": origin,
                "place": value,
            },
        })

    for sentence in _sentences(text):
        lowered_sentence = sentence.casefold()

        if not any(
            keyword in lowered_sentence
            for keyword in PLACE_KEYWORDS
        ):
            continue

        if len(sentence) < 8:
            continue

        evidence.append({
            "kind": "place_mention",
            "label": "Упоминание места в тексте",
            "text": sentence[:240],
            "confidence": 0.4,
            "country_hints": {},
            "details": {
                "origin": origin,
            },
        })

    for name, (country, category) in BRANDS.items():
        if name not in lowered:
            continue

        evidence.append({
            "kind": "business",
            "label": "Бренд или организация",
            "text": f"{name} ({category})",
            "confidence": 0.5,
            "country_hints": {country: 0.3},
            "details": {
                "origin": origin,
                "brand": name,
                "category": category,
            },
        })

    for country, pattern in LEGAL_FORMS:
        match = pattern.search(text)

        if not match:
            continue

        evidence.append({
            "kind": "business",
            "label": "Организационно-правовая форма",
            "text": match.group(0),
            "confidence": 0.3,
            "country_hints": {country: 0.15},
            "details": {
                "origin": origin,
                "legal_form": match.group(0),
            },
        })

    for match in URL_PATTERN.finditer(text):
        url = match.group(0).rstrip(".,;:!?)")

        evidence.append({
            "kind": "link",
            "label": "Внешняя ссылка",
            "text": url,
            "confidence": 0.75,
            "country_hints": _domain_hints(url),
            "details": {
                "origin": origin,
                "url": url,
            },
        })

    url_spans = [
        (match.start(), match.end())
        for match in URL_PATTERN.finditer(text)
    ]

    for match in BARE_DOMAIN_PATTERN.finditer(text):
        if any(
            start <= match.start() < end
            for start, end in url_spans
        ):
            continue

        domain = match.group(0).casefold()

        evidence.append({
            "kind": "link",
            "label": "Домен в тексте",
            "text": domain,
            "confidence": 0.5,
            "country_hints": _domain_hints(domain),
            "details": {
                "origin": origin,
                "url": domain,
            },
        })

    for match in PHONE_PATTERN.finditer(text):
        raw = " ".join(match.group(0).split())
        digits = re.sub(r"\D", "", raw)

        if not 10 <= len(digits) <= 15:
            continue

        country = _phone_country(digits)

        evidence.append({
            "kind": "phone",
            "label": "Телефон",
            "text": raw,
            "confidence": 0.45,
            "country_hints": {country: 0.3} if country else {},
            "details": {
                "origin": origin,
                "digits": digits,
                "country": country,
            },
        })

    for country, pattern in LICENSE_PLATE_PATTERNS:
        match = pattern.search(text)

        if not match:
            continue

        evidence.append({
            "kind": "license_plate",
            "label": "Возможный номерной знак",
            "text": match.group(0),
            "confidence": 0.4,
            "country_hints": {country: 0.25},
            "details": {
                "origin": origin,
                "country": country,
            },
        })

    for country, pattern in CURRENCY_PATTERNS:
        match = pattern.search(text)

        if not match:
            continue

        evidence.append({
            "kind": "currency",
            "label": "Валюта или денежная единица",
            "text": match.group(0),
            "confidence": 0.4,
            "country_hints": {country: 0.25},
            "details": {
                "origin": origin,
                "country": country,
            },
        })

    for match in TRANSPORT_PATTERN.finditer(text):
        value = " ".join(match.group(0).split())

        evidence.append({
            "kind": "transport",
            "label": "Транспорт или остановка",
            "text": value[:120],
            "confidence": 0.3,
            "country_hints": {},
            "details": {
                "origin": origin,
            },
        })

    for match in UNIT_PATTERN.finditer(text):
        value = match.group(0)

        hints = {}

        if "°F" in value:
            hints = {"US": 0.08}

        evidence.append({
            "kind": "units",
            "label": "Единицы измерения",
            "text": value,
            "confidence": 0.2,
            "country_hints": hints,
            "details": {
                "origin": origin,
            },
        })

    script = _script_hint(text)

    if script:
        evidence.append(script)

    for match in POSTAL_PATTERN.finditer(text):
        before = lowered[
            max(0, match.start() - 40):match.start()
        ]

        if not any(
            keyword in before
            for keyword in ("индекс", "почт", "index")
        ):
            continue

        evidence.append({
            "kind": "postal_code",
            "label": "Почтовый индекс",
            "text": match.group(0),
            "confidence": 0.5,
            "country_hints": {},
            "details": {
                "origin": origin,
            },
        })

    return evidence


def device_evidence(device: str | None) -> list[dict]:
    if not device:
        return []

    lowered = device.casefold()
    hints = {}

    for name, country in DEVICE_COUNTRIES.items():
        if name in lowered:
            hints = {country: 0.1}
            break

    return [{
        "kind": "device",
        "label": "Устройство съёмки",
        "text": device,
        "confidence": 0.5,
        "country_hints": hints,
        "details": {
            "origin": "metadata",
        },
    }]


def summarize(
    evidence: list[dict],
    profile: dict,
    duration: float = 0.0,
) -> dict:
    counts = Counter(item["kind"] for item in evidence)

    coordinates = [
        {
            "latitude": item["details"]["latitude"],
            "longitude": item["details"]["longitude"],
            "origin": item["details"].get("origin"),
        }
        for item in evidence
        if item["kind"] == "coordinates"
        and "latitude" in item.get("details", {})
    ]

    countries = {}

    for item in evidence:
        for code, weight in item.get(
            "country_hints",
            {},
        ).items():
            entry = countries.setdefault(
                code,
                {"score": 0.0, "signals": []},
            )

            entry["score"] += weight * (
                0.5 + item.get("confidence", 0.5)
            )

            signal = (
                f"{item['label']}: "
                f"{item['text'][:90]}"
            )

            if signal not in entry["signals"]:
                entry["signals"].append(signal)

    country_candidates = _normalize_countries(countries)

    places = {}

    for item in evidence:
        if item["kind"] not in ("address", "place_mention"):
            continue

        place = str(
            item.get("details", {}).get("place")
            or item.get("text")
            or ""
        ).strip()

        if len(place) < 5:
            continue

        entry = places.setdefault(
            place,
            {
                "count": 0,
                "confidence": 0.0,
                "kinds": set(),
            },
        )

        entry["count"] += 1
        entry["confidence"] = max(
            entry["confidence"],
            item.get("confidence", 0.0),
        )
        entry["kinds"].add(item["kind"])

    place_candidates = sorted(
        (
            {
                "text": text,
                "count": value["count"],
                "confidence": round(
                    min(0.95, value["confidence"] + 0.05 * (value["count"] - 1)),
                    2,
                ),
                "kinds": sorted(value["kinds"]),
            }
            for text, value in places.items()
        ),
        key=lambda item: (
            -item["confidence"],
            -item["count"],
        ),
    )[:8]

    search_queries = _search_queries(
        evidence,
        coordinates,
        place_candidates,
        country_candidates,
    )

    # Байесовская агрегация слабых улик: лог-правдоподобие по
    # ортогональным каналам вместо среднего confidence.
    from app.services.weakCluesService import aggregation as weak_aggregation

    aggregation = weak_aggregation.aggregate(evidence, duration)

    summary = (
        f"Собрано географических признаков: {len(evidence)}. "
        f"GPS: {counts.get('coordinates', 0)}; "
        f"адреса: {counts.get('address', 0)}; "
        f"места: {counts.get('place_mention', 0)}; "
        f"бренды: {counts.get('business', 0)}; "
        f"ссылки: {counts.get('link', 0)}; "
        f"телефоны: {counts.get('phone', 0)}. "
        f"Ортогональных каналов: "
        f"{aggregation.get('orthogonal_channels', 0)}; "
        f"дорожных кандидатов: "
        f"{aggregation.get('road_candidate_count', 0)}."
    )

    return {
        "coordinates": coordinates[:20],
        "country_candidates": country_candidates,
        "place_candidates": place_candidates,
        "search_queries": search_queries,
        "evidence_counts": dict(counts),
        "aggregation": aggregation,
        "road_candidates": aggregation.get("road_candidates", []),
        "orthogonal_channels": aggregation.get(
            "orthogonal_channels",
            0,
        ),
        "profile": profile,
        "summary": summary,
        "limitations": (
            "Признаки указывают на вероятную страну, регион "
            "или объект, но не подтверждают место съёмки. "
            "Проверяйте каждый сигнал вручную. Совпадение "
            "бренда, телефона или языка не является адресом. "
            "Визуальный профиль и геометрия дороги — "
            "предварительные оценки, а не координаты."
        ),
    }


def _normalize_countries(countries: dict) -> list[dict]:
    if not countries:
        return []

    top = max(value["score"] for value in countries.values())

    if top <= 0:
        return []

    result = []

    for code, value in sorted(
        countries.items(),
        key=lambda item: -item[1]["score"],
    ):
        score = value["score"] / top

        if score < 0.25:
            continue

        result.append({
            "code": code,
            "name": COUNTRY_NAMES.get(code, code),
            "score": round(score, 2),
            "signals": value["signals"][:6],
        })

        if len(result) >= 5:
            break

    return result


def _search_queries(
    evidence: list[dict],
    coordinates: list[dict],
    places: list[dict],
    countries: list[dict],
) -> list[str]:
    queries = []

    def add(value: str) -> None:
        value = " ".join(value.split()).strip(" .,;")

        if value and value not in queries:
            queries.append(value[:160])

    for item in coordinates[:3]:
        add(
            f"{item['latitude']:.6f}, "
            f"{item['longitude']:.6f}"
        )

    for item in places[:5]:
        add(item["text"])

    brands = [
        item["details"].get("brand")
        or item["text"]
        for item in evidence
        if item["kind"] == "business"
    ]

    for brand in brands[:4]:
        if places:
            add(f"{brand}, {places[0]['text']}")
        else:
            add(str(brand))

    for item in evidence:
        if item["kind"] == "address":
            add(item["text"])

        if len(queries) >= 8:
            break

    if not queries:
        for candidate in countries[:1]:
            add(
                "страна "
                + str(candidate.get("name", ""))
            )

    return queries[:8]


def _sentences(text: str) -> list[str]:
    parts = re.split(
        r"[.!?;\n•|]+",
        text,
    )

    return [
        " ".join(part.split())
        for part in parts
        if part.strip()
    ]


def _domain_hints(value: str) -> dict:
    host = str(value).casefold()

    host = re.sub(r"^https?://", "", host)
    host = re.sub(r"^www\.", "", host)
    host = host.split("/")[0].split(":")[0]

    if "." not in host:
        return {}

    tld = host.rsplit(".", 1)[-1]
    country = TLD_COUNTRIES.get(tld)

    if not country:
        return {}

    return {country: 0.3}


def _phone_country(digits: str) -> str | None:
    if not digits:
        return None

    if digits.startswith("7"):
        # +7 6xx/7xx чаще Казахстан, остальные — Россия.
        if len(digits) == 11 and digits[1] in ("6", "7"):
            return "KZ"

        return "RU"

    if digits.startswith("8") and len(digits) == 11:
        return "RU"

    for length in (3, 2, 1):
        prefix = digits[:length]
        country = dict(PHONE_PREFIXES).get(prefix)

        if country:
            return country

    return None


def _script_hint(text: str) -> dict | None:
    cyrillic = len(CYRILLIC_PATTERN.findall(text))
    latin = len(LATIN_PATTERN.findall(text))

    lowered = text.casefold()

    for country, chars in SPECIAL_SCRIPTS.items():
        if any(char in lowered for char in chars):
            return {
                "kind": "language",
                "label": "Язык и письменность",
                "text": (
                    "особые буквы: "
                    f"{COUNTRY_NAMES.get(country, country)}"
                ),
                "confidence": 0.4,
                "country_hints": {country: 0.3},
                "details": {
                    "origin": "text",
                    "script": country,
                },
            }

    if cyrillic >= 12:
        return {
            "kind": "language",
            "label": "Язык и письменность",
            "text": "кириллица",
            "confidence": 0.25,
            "country_hints": {},
            "details": {
                "origin": "text",
                "script": "cyrillic",
            },
        }

    if latin >= 20 and cyrillic == 0:
        return {
            "kind": "language",
            "label": "Язык и письменность",
            "text": "латиница",
            "confidence": 0.2,
            "country_hints": {},
            "details": {
                "origin": "text",
                "script": "latin",
            },
        }

    return None
