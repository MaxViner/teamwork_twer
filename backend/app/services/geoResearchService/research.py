"""Гео-исследование: от видимых признаков к слоям карт.

Отдельная задача, не связанная с обработкой видео. На входе —
видимые породы деревьев, ориентиры, следы деятельности и звуки.
На выходе — гипотеза региона по растительности, порядок слоёв
(OSM → Wikimapia → Генштаб → кадастр → спутник), ссылки на карты,
положение солнца и тени, триангуляция по известным ориентирам и
чек-лист перекрёстной проверки.

Это исследовательский инструмент, а не доказательство координат.
"""

from __future__ import annotations

import math
from datetime import date as date_type, datetime


TVE_CENTER = (56.8587, 35.9176)

EARTH_RADIUS_M = 6371008.8


SPECIES_ZONES = (
    {
        "zone": "southern_taiga",
        "label_ru": "южная тайга / смешанные леса",
        "keywords": ("ель", "сосна", "пихта", "кедр", "берёза", "береза", "осина", "ольха"),
        "regions": (
            "Тверская область",
            "Новгородская область",
            "Псковская область",
            "Смоленская область",
            "Ярославская область",
        ),
        "reason": (
            "Ель, сосна, берёза и осина образуют южно-таёжные и "
            "смешанные леса центра Русской равнины."
        ),
    },
    {
        "zone": "broadleaf_forest",
        "label_ru": "широколиственные леса",
        "keywords": ("дуб", "липа", "клён", "клен", "ясень", "вяз", "орешник", "лещина"),
        "regions": (
            "Тульская область",
            "Калужская область",
            "Орловская область",
            "Брянская область",
            "Липецкая область",
        ),
        "reason": (
            "Дуб, липа, клён и ясень тяготеют к широколиственным "
            "лесам лесостепной и переходной зоны."
        ),
    },
    {
        "zone": "forest_steppe",
        "label_ru": "лесостепь",
        "keywords": ("ковыль", "типчак", "терн", "тёрн", "боярышник", "степной"),
        "regions": (
            "Воронежская область",
            "Курская область",
            "Белгородская область",
            "Тамбовская область",
        ),
        "reason": (
            "Ковыль, типчак и колючие кустарники указывают на "
            "лесостепь и степь."
        ),
    },
    {
        "zone": "arid",
        "label_ru": "сухие степи и полупустыни",
        "keywords": ("саксаул", "верблюжья", "полынь", "джузгун", "солончак"),
        "regions": (
            "Астраханская область",
            "Волгоградская область",
            "Республика Калмыкия",
        ),
        "reason": (
            "Саксаул, полынь и солончаки характерны для сухих "
            "степей и полупустынь Прикаспия."
        ),
    },
    {
        "zone": "mountain",
        "label_ru": "горный пояс",
        "keywords": ("кедровый стланик", "рододендрон", "альпийский", "субальпийский", "лиственница"),
        "regions": (
            "Республика Алтай",
            "Краснодарский край",
            "Республика Северная Осетия — Алания",
            "Сахалинская область",
        ),
        "reason": (
            "Кедровый стланик, рододендрон и лиственница в верхнем "
            "поясе указывают на горные районы."
        ),
    },
)


LAYERS = (
    {
        "order": 1,
        "id": "osm",
        "name": "OpenStreetMap",
        "purpose": "Современные дороги, дома, ЛЭП и названия урочищ.",
    },
    {
        "order": 2,
        "id": "wikimapia",
        "name": "Wikimapia",
        "purpose": "Подписи заброшенных объектов, фундаментов и урочищ.",
    },
    {
        "order": 3,
        "id": "genshtab",
        "name": "Генштаб 1930–1980",
        "purpose": "Деревни, дороги и просеки, которых уже нет на OSM.",
    },
    {
        "order": 4,
        "id": "cadastre",
        "name": "Публичная кадастровая карта",
        "purpose": "Границы участков, категории земель и бывшие населённые пункты.",
    },
    {
        "order": 5,
        "id": "satellite",
        "name": "Спутник с историческим слайдером",
        "purpose": "Следы построек 2005–2010 годов и зарастание полей.",
    },
)


CROSS_CHECKS = (
    {
        "id": "tree",
        "label": "Одинокое дерево или группа деревьев",
        "why": "Проверить на спутнике и старых снимках: форма кроны и тень.",
    },
    {
        "id": "foundation",
        "label": "Фундамент, яма или просевший грунт",
        "why": "Сопоставить контур с планом деревни и кадастровыми границами.",
    },
    {
        "id": "roads",
        "label": "Развилка дорог или просек",
        "why": "Угол между дорогами — устойчивый признак на картах разных лет.",
    },
    {
        "id": "facade",
        "label": "Ориентация фасада и тень",
        "why": "Сверить с положением солнца и направлением улицы.",
    },
    {
        "id": "water",
        "label": "Изгиб берега, мост или брод",
        "why": "Сравнить с гидрографией OSM и старыми картами.",
    },
    {
        "id": "sound",
        "label": "Звук: церковь, поезд, вода, техника",
        "why": "Ограничить радиус поиска по слышимости и направлению.",
    },
)


def build_research(payload: dict) -> dict:
    """Собрать ответ исследовательской задачи."""

    species = _clean_list(payload.get("species"))
    landmarks = _clean_list(payload.get("landmarks"))
    traces = _clean_list(payload.get("traces"))
    sounds = _clean_list(payload.get("sounds"))
    region = _clean(payload.get("region"))
    district = _clean(payload.get("district"))

    latitude = _number(payload.get("latitude"))
    longitude = _number(payload.get("longitude"))

    region_hypothesis = _region_hypothesis(
        species,
        region,
        district,
    )

    triangulation = triangulate(
        payload.get("triangulation_points") or []
    )

    if triangulation.get("ok"):
        latitude = triangulation["latitude"]
        longitude = triangulation["longitude"]

    center = (
        (latitude, longitude)
        if latitude is not None and longitude is not None
        else None
    )

    sun = solar_position(
        latitude,
        longitude,
        payload.get("date"),
        payload.get("time"),
        payload.get("utc_offset", 3),
    )

    return {
        "schema_version": 1,
        "status": "research_hypothesis_not_geolocation",
        "visible_inventory": {
            "species": species,
            "landmarks": landmarks,
            "traces": traces,
            "sounds": sounds,
        },
        "region_hypothesis": region_hypothesis,
        "map": _map(center),
        "layer_plan": _layers(center),
        "sun": sun,
        "triangulation": triangulation,
        "cross_checks": [
            {**item, "done": False}
            for item in CROSS_CHECKS
        ],
        "vanished_villages": _vanished_villages(),
        "next_steps": _next_steps(
            region_hypothesis,
            triangulation,
            center,
        ),
        "limits": [
            "Растительность даёт зону, а не точку.",
            "Слои карт нужно проверять вручную: переименования и "
            "слившиеся деревни дают ложные совпадения.",
            "Триангуляция работает только по известным ориентирам "
            "с координатами и азимутами.",
        ],
    }


def _clean_list(value) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []

    return [
        str(item).strip()
        for item in value
        if str(item).strip()
    ]


def _clean(value) -> str | None:
    text = str(value or "").strip()
    return text or None


def _number(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _region_hypothesis(
    species: list[str],
    region: str | None,
    district: str | None,
) -> dict:
    text = " ".join(species).lower()

    matches = []

    for zone in SPECIES_ZONES:
        found = [
            keyword
            for keyword in zone["keywords"]
            if keyword in text
        ]

        if found:
            matches.append((zone, found))

    if not matches:
        return {
            "region": region,
            "district": district,
            "vegetation_zone": "unknown",
            "zone_label_ru": "не определена",
            "confidence": "low",
            "candidate_regions": [],
            "reasoning": [
                "Недостаточно данных о породах деревьев. "
                "Укажите хотя бы 2–3 видимых вида."
            ],
        }

    matches.sort(key=lambda item: -len(item[1]))
    zone, found = matches[0]
    confidence = "high" if len(found) >= 2 else "medium"

    reasoning = [
        zone["reason"],
        "Найдены признаки: " + ", ".join(found) + ".",
    ]

    if region:
        reasoning.append(
            f"Пользователь указал регион: {region}. "
            "Проверьте, согласуется ли он с растительностью."
        )

    if district:
        reasoning.append(
            f"Район для сужения: {district}. Границы лесничеств "
            "публичны и помогут отсечь лишние квадраты."
        )

    return {
        "region": region or zone["regions"][0],
        "district": district,
        "vegetation_zone": zone["zone"],
        "zone_label_ru": zone["label_ru"],
        "confidence": confidence,
        "candidate_regions": list(zone["regions"]),
        "reasoning": reasoning,
    }


def _map(center: tuple[float, float] | None) -> dict:
    latitude, longitude = center or TVE_CENTER
    delta_lat = 0.03 if center else 0.8
    delta_lon = 0.05 if center else 1.2
    zoom = 14 if center else 7

    bbox = (
        longitude - delta_lon,
        latitude - delta_lat,
        longitude + delta_lon,
        latitude + delta_lat,
    )

    embed = (
        "https://www.openstreetmap.org/export/embed.html"
        f"?bbox={bbox[0]:.6f},{bbox[1]:.6f},"
        f"{bbox[2]:.6f},{bbox[3]:.6f}"
        "&layer=mapnik"
        f"&marker={latitude:.6f},{longitude:.6f}"
    )

    return {
        "latitude": round(latitude, 6),
        "longitude": round(longitude, 6),
        "zoom": zoom,
        "center_is_hypothesis": center is not None,
        "bbox": [round(value, 6) for value in bbox],
        "embed_url": embed,
    }


def _layers(center: tuple[float, float] | None) -> list[dict]:
    latitude, longitude = center or TVE_CENTER

    urls = {
        "osm": (
            f"https://www.openstreetmap.org/#map=14/"
            f"{latitude:.6f}/{longitude:.6f}"
        ),
        "wikimapia": (
            "http://wikimapia.org/#lang=ru"
            f"&lat={latitude:.6f}&lon={longitude:.6f}&z=14"
        ),
        "genshtab": "https://retromap.ru/",
        "cadastre": "https://pkk.rosreestr.ru/",
        "satellite": (
            f"https://yandex.ru/maps/?ll={longitude:.6f}%2C"
            f"{latitude:.6f}&z=15&l=sat"
        ),
    }

    return [
        {
            **layer,
            "url": urls[layer["id"]],
        }
        for layer in LAYERS
    ]


def _vanished_villages() -> dict:
    return {
        "title": "Метод вычитания слоёв для исчезнувших деревень",
        "steps": [
            "Собрать старые карты: Менде, межевые планы, Генштаб 1930–1980.",
            "Выписать населённые пункты из списков XIX века и справочника АТД 1970–80-х.",
            "Выгрузить современные НП из OSM/ОКТМО.",
            "Сопоставить по району, а не по области: названия повторяются.",
            "Отметить пары «есть в старом списке, нет в новом» — кандидаты.",
            "Проверить кандидатов по спутнику 2005–2010 и кадастровой карте.",
            "Отсеять переименования и слившиеся деревни ручной проверкой.",
        ],
        "sources": [
            {"name": "Retromap", "url": "https://retromap.ru/"},
            {"name": "Etomesto", "url": "https://www.etomesto.com/"},
            {"name": "Публичная кадастровая карта", "url": "https://pkk.rosreestr.ru/"},
            {"name": "Overpass API", "url": "https://overpass-turbo.eu/"},
        ],
    }


def _next_steps(
    hypothesis: dict,
    triangulation: dict,
    center: tuple[float, float] | None,
) -> list[str]:
    steps = [
        "Заполнить инвентарь: породы деревьев, ориентиры горизонта, "
        "следы деятельности и звуки.",
        "Сузить регион по растительности, затем — по лесничествам.",
        "Прогнать кандидата через OSM → Wikimapia → Генштаб → "
        "кадастр → спутник с историческим слайдером.",
    ]

    if hypothesis.get("district"):
        steps.append(
            f"Проверить границы лесничеств в районе "
            f"«{hypothesis['district']}»."
        )

    if triangulation.get("ok"):
        steps.append(
            "Сверить точку триангуляции с ориентирами на месте "
            "и оценить невязку."
        )
    else:
        steps.append(
            "Добавить 2+ известных ориентира с координатами и "
            "азимутами, чтобы получить точку триангуляции."
        )

    if center:
        steps.append(
            "Открыть спутник и старые карты вокруг предполагаемой "
            "точки, проверить тени и уникальные объекты."
        )
    else:
        steps.append(
            "Пока нет координат: начните с области-кандидата и "
            "постепенно сужайте по уникальным объектам."
        )

    return steps


def solar_position(
    latitude: float | None,
    longitude: float | None,
    date_value,
    time_value,
    utc_offset=3,
) -> dict | None:
    """Приблизительное положение солнца и направление тени.

    Формула NOAA достаточна, чтобы понять, куда падает тень на
    снимке и с какой стороны искать фасад.
    """

    if latitude is None or longitude is None:
        return None

    day = _parse_date(date_value)

    if day is None:
        return None

    hour, minute = _parse_time(time_value)

    try:
        utc_offset = float(utc_offset)
    except (TypeError, ValueError):
        utc_offset = 3.0

    day_of_year = day.timetuple().tm_yday
    gamma = 2.0 * math.pi / 365.0 * (
        day_of_year - 1 + (hour - 12) / 24.0
    )

    equation_of_time = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )

    declination = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )

    time_offset = (
        equation_of_time
        + 4.0 * longitude
        - 60.0 * utc_offset
    )

    true_solar_time = hour * 60.0 + minute + time_offset
    hour_angle = math.radians(
        true_solar_time / 4.0 - 180.0
    )

    lat = math.radians(latitude)

    cos_zenith = (
        math.sin(lat) * math.sin(declination)
        + math.cos(lat) * math.cos(declination)
        * math.cos(hour_angle)
    )
    cos_zenith = max(-1.0, min(1.0, cos_zenith))

    zenith = math.acos(cos_zenith)
    elevation = 90.0 - math.degrees(zenith)

    azimuth = math.degrees(math.atan2(
        math.sin(hour_angle),
        math.cos(hour_angle) * math.sin(lat)
        - math.tan(declination) * math.cos(lat),
    )) + 180.0
    azimuth %= 360.0

    if elevation <= 0:
        return {
            "sun_azimuth_deg": round(azimuth, 1),
            "sun_elevation_deg": round(elevation, 1),
            "shadow_azimuth_deg": None,
            "shadow_length_ratio": None,
            "note": "Солнце ниже горизонта: тень не анализируется.",
        }

    shadow_azimuth = (azimuth + 180.0) % 360.0
    shadow_ratio = 1.0 / math.tan(math.radians(elevation))

    return {
        "sun_azimuth_deg": round(azimuth, 1),
        "sun_elevation_deg": round(elevation, 1),
        "shadow_azimuth_deg": round(shadow_azimuth, 1),
        "shadow_length_ratio": round(shadow_ratio, 2),
        "note": (
            "Тень падает в направлении shadow_azimuth_deg; "
            "длина тени ≈ высота объекта × shadow_length_ratio."
        ),
    }


def _parse_date(value) -> date_type | None:
    if not value:
        return None

    text = str(value).strip()

    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    return None


def _parse_time(value) -> tuple[int, int]:
    if not value:
        return 12, 0

    text = str(value).strip()

    for fmt in ("%H:%M", "%H.%M"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.hour, parsed.minute
        except ValueError:
            continue

    return 12, 0


def triangulate(points) -> dict:
    """Пересечь лучи от известных ориентиров.

    points: [{name, lat, lon, azimuth}], где azimuth — направление
    от камеры на ориентир (0° = север, 90° = восток).
    """

    cleaned = []

    for item in points if isinstance(points, list) else []:
        if not isinstance(item, dict):
            continue

        latitude = _number(item.get("lat"))
        longitude = _number(item.get("lon"))
        azimuth = _number(item.get("azimuth"))

        if (
            latitude is None
            or longitude is None
            or azimuth is None
        ):
            continue

        cleaned.append({
            "name": item.get("name") or f"точка {len(cleaned) + 1}",
            "lat": latitude,
            "lon": longitude,
            "azimuth": azimuth % 360.0,
        })

    if len(cleaned) < 2:
        return {
            "ok": False,
            "reason": "Нужны минимум 2 ориентира с координатами и азимутами.",
        }

    lat0 = sum(item["lat"] for item in cleaned) / len(cleaned)
    lon0 = sum(item["lon"] for item in cleaned) / len(cleaned)

    local = [
        _to_local(item["lat"], item["lon"], lat0, lon0)
        for item in cleaned
    ]

    intersections = []

    for first in range(len(local)):
        for second in range(first + 1, len(local)):
            point = _intersect(
                local[first],
                cleaned[first]["azimuth"],
                local[second],
                cleaned[second]["azimuth"],
            )

            if point is not None:
                intersections.append(point)

    if not intersections:
        return {
            "ok": False,
            "reason": "Лучи параллельны или почти параллельны: точки не пересекаются.",
        }

    x = sum(item[0] for item in intersections) / len(intersections)
    y = sum(item[1] for item in intersections) / len(intersections)

    spread = 0.0

    for item in intersections:
        spread = max(
            spread,
            math.hypot(item[0] - x, item[1] - y),
        )

    latitude, longitude = _from_local(x, y, lat0, lon0)

    return {
        "ok": True,
        "latitude": round(latitude, 6),
        "longitude": round(longitude, 6),
        "points_used": len(cleaned),
        "intersections": len(intersections),
        "spread_m": round(spread, 1),
        "method": (
            "Пересечение обратных лучей от известных ориентиров; "
            "азимут задан от камеры на ориентир."
        ),
        "note": (
            "Чем меньше spread_m, тем согласованнее азимуты. "
            "Проверьте результат на карте."
        ),
    }


def _to_local(
    latitude: float,
    longitude: float,
    lat0: float,
    lon0: float,
) -> tuple[float, float]:
    x = EARTH_RADIUS_M * math.radians(longitude - lon0) * math.cos(
        math.radians(lat0)
    )
    y = EARTH_RADIUS_M * math.radians(latitude - lat0)

    return x, y


def _from_local(
    x: float,
    y: float,
    lat0: float,
    lon0: float,
) -> tuple[float, float]:
    latitude = lat0 + math.degrees(y / EARTH_RADIUS_M)
    longitude = lon0 + math.degrees(
        x / (EARTH_RADIUS_M * math.cos(math.radians(lat0)))
    )

    return latitude, longitude


def _intersect(
    first: tuple[float, float],
    first_azimuth: float,
    second: tuple[float, float],
    second_azimuth: float,
) -> tuple[float, float] | None:
    # Камера лежит в обратном направлении от ориентира.
    d1 = _direction(first_azimuth + 180.0)
    d2 = _direction(second_azimuth + 180.0)

    denominator = d1[0] * d2[1] - d1[1] * d2[0]

    if abs(denominator) < 1e-9:
        return None

    delta_x = second[0] - first[0]
    delta_y = second[1] - first[1]

    t = (delta_x * d2[1] - delta_y * d2[0]) / denominator

    return (
        first[0] + t * d1[0],
        first[1] + t * d1[1],
    )


def _direction(azimuth: float) -> tuple[float, float]:
    radians = math.radians(azimuth % 360.0)

    return math.sin(radians), math.cos(radians)
