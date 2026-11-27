"""Карта «привидений» Тверской губернии.

Отдельный сервис, не связанный с анализом видео. Он переносит
логику исследовательского скрипта ``tver_ghosts.py`` в модуль с
двумя точками входа:

- ``run_generation(options)`` — полный прогон: загрузка списков СНМ
  1859 г., парсинг, сопоставление с современными НП OSM, необязательный
  Nominatim, запись артефактов;
- ``read_outputs()`` — чтение уже готовых артефактов без пересчёта.

Артефакты лежат в ``data/ghost_map/`` (не в папках заданий). Долгая
генерация выполняется в фоновом потоке, поэтому HTTP-запрос не
блокируется. Сетевые ошибки не роняют приложение: статус получает
состояние ``failed`` и понятное сообщение.
"""

from __future__ import annotations

import csv
import difflib
import json
import os
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Callable

import requests

from app.config import DATA_DIR


ROOT = Path(
    os.getenv(
        "GHOST_MAP_DIR",
        str(DATA_DIR / "ghost_map"),
    )
)

PLACES_FILE = ROOT / "snm_1859_all.geojson"
GHOSTS_FILE = ROOT / "ghosts.geojson"
UNRESOLVED_FILE = ROOT / "unresolved.csv"
GEOCACHE_FILE = ROOT / "geocache.json"
META_FILE = ROOT / "meta.json"
MARKS_FILE = ROOT / "marks.json"
STATUS_FILE = ROOT / "status.json"
LOG_FILE = ROOT / "last_run.log"

CACHE_DIR = ROOT / "raw_html"
OSM_CACHE_FILE = ROOT / "osm_places_tver.json"

USER_AGENT = {
    "User-Agent": "video-service-ghost-map/1.0 (local research)",
}

OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)

POMNIROD_TPL = (
    "https://pomnirod.ru/materialy-k-statyam/"
    "administrativno-territorialnoe-delenie-rossijskoj-imperii/"
    "gubernii-rossii/tverskaya-guberniya/naselennye-mesta-gubernii/"
    "{slug}/naselennye-mesta-{slug}/spisok-naselennyh-mest-{uzda}-za-1859-g.html"
)

# 12 уездов Тверской губернии по списку 1859/1862 гг.
UYEZDS = {
    "тверской": "tverskoj-uezd-tverskoj-gubernii",
    "бежецкий": "bezhetskij-uezd-tverskoj-gubernii",
    "весьегонский": "vesegonskij-uezd-tverskoj-gubernii",
    "вышневолоцкий": "vyshnevolockij-uezd-tverskoj-gubernii",
    "зубцовский": "zubcovskij-uezd-tverskoj-gubernii",
    "калязинский": "kalyazinskij-uezd-tverskoj-gubernii",
    "кашинский": "kashinskij-uezd-tverskoj-gubernii",
    "корчевский": "korchewskij-uezd-tverskoj-gubernii",
    "новоторжский": "novotorzhskij-uezd-tverskoj-gubernii",
    "осташковский": "ostashkovskij-uezd-tverskoj-gubernii",
    "ржевский": "rzhevskij-uezd-tverskoj-gubernii",
    "старицкий": "starickij-uezd-tverskoj-gubernii",
}

ROW_RE = re.compile(
    r"^(?:\d{1,5}[.)]?\s+)?"
    r"(?P<name>[А-ЯЁ][^0-9(]+?)(?:\s*\((?P<alias>[^)]+)\))?\s+"
    r"(?P<kind>с\.|д\.|сц\.|пог\.|хут\.|высел\.|сл\.|скот\.\s*дв\.)\s*"
    r"(?:(?P<type>[А-Яа-я][А-Яа-я. ]{0,20}?)\s+)?"
    r"при\s+(?P<position>[^0-9]+?)\s*"
    r"(?P<nums>[\d\s.]+)$",
    re.MULTILINE | re.IGNORECASE,
)


class GhostMapError(RuntimeError):
    """Понятная ошибка генерации для API и лога."""


class GenerationBusy(GhostMapError):
    """Попытка запустить вторую генерацию одновременно."""


_LOCK = RLock()
_EXECUTOR = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="ghost-map",
)
_GEOCACHE: dict | None = None
_ROADS_CACHE: dict[tuple, tuple[float, dict]] = {}
_ROADS_TTL = 600.0


# ──────────────────────────────────────────────────────────── статус


def ensure_dirs() -> None:
    """Создать каталог артефактов и кэшей."""

    ROOT.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))

    except (OSError, ValueError):
        return default


def _write_json(path: Path, payload) -> None:
    ensure_dirs()
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _initial_status() -> dict:
    saved = _read_json(STATUS_FILE, {}) or {}

    if saved.get("running"):
        # Прошлый процесс завершился, не успев закрыть прогон.
        saved.update(
            running=False,
            state="interrupted",
            message="Предыдущая генерация прервана перезапуском.",
            finished_at=saved.get("finished_at") or _now(),
        )

    return {
        "running": False,
        "state": "idle",
        "progress": 0,
        "message": "Генерация ещё не запускалась.",
        "started_at": None,
        "finished_at": None,
        "error": None,
        **saved,
    }


_STATUS = _initial_status()


def _set_status(**patch) -> None:
    with _LOCK:
        _STATUS.update(patch)

        try:
            _write_json(STATUS_FILE, _STATUS)

        except OSError:
            pass


def status() -> dict:
    """Текущее состояние фоновой генерации и метаданные."""

    with _LOCK:
        payload = dict(_STATUS)

    payload["meta"] = _read_json(META_FILE, None)
    payload["uyezds"] = list(UYEZDS)

    return payload


def _log(message: str) -> None:
    ensure_dirs()

    line = f"{_now()} {message}"

    try:
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    except OSError:
        pass


# ──────────────────────────────────────────────────────────── сеть


def uyezd_url(name: str) -> str:
    """Собрать URL страницы СНМ для уезда."""

    slug = UYEZDS[name]
    uzda = slug.split("-uezd")[0]

    if uzda.endswith("skij"):
        uzda = uzda[:-4] + "skogo"

    elif uzda.endswith("ij"):
        uzda = uzda[:-2] + "ogo"

    return POMNIROD_TPL.format(slug=slug, uzda=uzda)


def fetch_html(url: str, cache_name: str) -> str | None:
    """Скачать HTML с кэшем; при ошибке вернуть None."""

    ensure_dirs()
    cache = CACHE_DIR / cache_name

    if cache.is_file():
        return cache.read_text(encoding="utf-8")

    try:
        response = requests.get(
            url,
            headers=USER_AGENT,
            timeout=30,
        )

        if response.status_code == 200 and len(response.text) > 3000:
            cache.write_text(response.text, encoding="utf-8")
            time.sleep(1.5)
            return response.text

        _log(f"pomnirod: HTTP {response.status_code} для {url}")

    except Exception as error:
        _log(f"pomnirod: сеть недоступна ({error})")

    return None


def _overpass(query: str, timeout: int) -> dict:
    """Выполнить Overpass-запрос с перебором зеркал."""

    last_error = None

    for url in OVERPASS_URLS:
        try:
            response = requests.post(
                url,
                data={"data": query},
                headers=USER_AGENT,
                timeout=timeout,
            )

            if response.status_code == 200:
                return response.json()

            last_error = f"HTTP {response.status_code}"

        except Exception as error:
            last_error = str(error)

        _log(f"overpass {url}: {last_error}")

    raise GhostMapError(
        "Overpass недоступен: "
        f"{last_error or 'нет ответа'}. "
        "Проверьте сеть или положите кэш osm_places_tver.json."
    )


def fetch_modern_places() -> list[dict]:
    """Современные деревни Тверской области из OSM (с кэшем)."""

    ensure_dirs()

    if OSM_CACHE_FILE.is_file():
        cached = _read_json(OSM_CACHE_FILE, {}) or {}
        elements = cached.get("elements")

        if elements:
            return elements

    query = """
[out:json][timeout:300];
area["ISO3166-2"="RU-TVE"]->.a;
nwr(area.a)[place~"^(village|hamlet|town)$"];
out center tags;
"""

    data = _overpass(query, timeout=300)
    _write_json(OSM_CACHE_FILE, data)

    return data.get("elements") or []


def _geocache() -> dict:
    global _GEOCACHE

    if _GEOCACHE is None:
        _GEOCACHE = _read_json(GEOCACHE_FILE, {}) or {}

    return _GEOCACHE


def geocode(name: str) -> list[dict]:
    """Nominatim в границах Тверской области, с кэшем и паузой."""

    cache = _geocache()
    key = normalize_name(name)

    if key in cache:
        return cache[key]

    params = {
        "q": f"{name}, Тверская область, Россия",
        "format": "jsonv2",
        "limit": 3,
        "countrycodes": "ru",
        "viewbox": "31.0,58.9,38.6,56.2",
        "bounded": 1,
    }

    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params=params,
            headers=USER_AGENT,
            timeout=20,
        )

        if response.status_code == 200:
            result = [
                {
                    "lat": float(item["lat"]),
                    "lon": float(item["lon"]),
                    "display": item.get("display_name", ""),
                }
                for item in response.json()
            ]

        else:
            result = []

    except Exception as error:
        _log(f"nominatim {name}: {error}")
        result = []

    cache[key] = result
    _write_json(GEOCACHE_FILE, cache)

    # Лимит Nominatim: не больше одного запроса в секунду.
    time.sleep(1.1)

    return result


# ──────────────────────────────────────────────────────────── парсинг


def parse_snm(html: str) -> list[dict]:
    """Разобрать таблицу СНМ в список населённых мест."""

    rows = []

    for match in ROW_RE.finditer(html):
        name = match.group("name").strip().strip(",;")

        if not name or len(name) < 3:
            continue

        numbers = [
            float(value)
            for value in re.findall(
                r"\d+(?:\.\d+)?",
                match.group("nums"),
            )
        ]

        rows.append({
            "name": name,
            "alias": (match.group("alias") or "").strip() or None,
            "kind": match.group("kind").strip(),
            "position": match.group("position").strip(" .,"),
            "numbers": numbers,
        })

    return rows


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = value.replace("ё", "е")
    value = value.replace("ій", "ий").replace("ый", "ий")
    value = re.sub(r"[^а-я a-z]", "", value)

    return re.sub(r"\s+", " ", value).strip()


def levenshtein(first: str, second: str) -> int:
    if first == second:
        return 0

    if len(first) < len(second):
        first, second = second, first

    previous = list(range(len(second) + 1))

    for i, left in enumerate(first, 1):
        current = [i]

        for j, right in enumerate(second, 1):
            current.append(min(
                previous[j] + 1,
                current[j - 1] + 1,
                previous[j - 1] + (left != right),
            ))

        previous = current

    return previous[-1]


def to_geojson(items: list[dict]) -> dict:
    features = []

    for item in items:
        if item.get("lat") is None or item.get("lon") is None:
            continue

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [item["lon"], item["lat"]],
            },
            "properties": {
                key: value
                for key, value in item.items()
                if key not in ("lat", "lon")
            },
        })

    return {"type": "FeatureCollection", "features": features}


def _empty_collection() -> dict:
    return {"type": "FeatureCollection", "features": []}


# ──────────────────────────────────────────────────────────── генерация


def run_generation(options: dict | None = None) -> dict:
    """Полный прогон: fetch → parse → match → outputs.

    Синхронная функция. Её вызывает фоновый поток, но её можно
    вызвать и напрямую из теста.
    """

    options = dict(options or {})
    use_nominatim = bool(options.get("use_nominatim"))
    skip_fetch = bool(options.get("skip_fetch"))
    requested = str(options.get("uyezd") or "").strip().lower()

    ensure_dirs()

    if requested:
        names = [
            name
            for name in UYEZDS
            if requested in name
        ]

        if not names:
            raise GhostMapError(
                f"Неизвестный уезд: {options.get('uyezd')}. "
                f"Доступны: {', '.join(UYEZDS)}."
            )

    else:
        names = list(UYEZDS)

    _log(f"СТАРТ генерации: уезды={names}, nominatim={use_nominatim}")
    _set_status(
        progress=1,
        message="Загрузка списков СНМ 1859 г.",
    )

    all_rows: list[dict] = []

    for index, name in enumerate(names):
        _set_status(
            progress=2 + 20 * index / max(len(names), 1),
            message=f"СНМ: {name}",
        )

        if skip_fetch:
            cache = CACHE_DIR / f"{name}.html"
            html = (
                cache.read_text(encoding="utf-8")
                if cache.is_file()
                else None
            )

            if html is None:
                _log(f"{name}: нет кэша raw_html/{name}.html")
                continue

        else:
            html = fetch_html(uyezd_url(name), f"{name}.html")

        if html is None:
            _log(f"{name}: страница не получена, пропуск")
            continue

        rows = parse_snm(html)

        for row in rows:
            row["uyezd"] = name

        all_rows.extend(rows)
        _log(f"{name}: распарсено {len(rows)} НП")

    if not all_rows:
        raise GhostMapError(
            "Не распарсено ни одной строки. Проверьте доступ к "
            "pomnirod.ru или положите HTML в data/ghost_map/raw_html/."
        )

    _set_status(
        progress=25,
        message=f"Загружено НП: {len(all_rows)}. Загрузка OSM…",
    )

    modern = []

    for element in fetch_modern_places():
        tags = element.get("tags", {})
        name = tags.get("name")

        if not name:
            continue

        lat = element.get("lat") or element.get("center", {}).get("lat")
        lon = element.get("lon") or element.get("center", {}).get("lon")

        if lat is None or lon is None:
            continue

        modern.append({
            "name": name,
            "lat": float(lat),
            "lon": float(lon),
            "place": tags.get("place", ""),
        })

    _set_status(
        progress=40,
        message=f"Современных НП OSM: {len(modern)}. Сопоставление…",
    )

    by_name: dict[str, list[dict]] = {}

    for item in modern:
        by_name.setdefault(normalize_name(item["name"]), []).append(item)

    matched: list[dict] = []
    ghosts: list[dict] = []
    unresolved: list[dict] = []

    total = len(all_rows)
    geocoded = 0

    for index, row in enumerate(all_rows):
        normalized = normalize_name(row["name"])
        candidates = by_name.get(normalized, [])
        hit = candidates[0] if candidates else None

        if len(candidates) > 1:
            row["ambiguous"] = True

        if hit is None:
            best = difflib.get_close_matches(
                normalized,
                list(by_name),
                n=1,
                cutoff=0.88,
            )

            if best:
                hit = by_name[best[0]][0]
                row["fuzzy"] = True

        if hit is not None:
            row.update(
                lat=hit["lat"],
                lon=hit["lon"],
                match="osm",
                modern_name=hit["name"],
            )
            matched.append(row)
            continue

        ghost = dict(row)

        if use_nominatim:
            result = geocode(row["name"])
            geocoded += 1

            if result:
                ghost.update(
                    lat=result[0]["lat"],
                    lon=result[0]["lon"],
                    match="nominatim",
                    modern_name=result[0]["display"],
                    approximate=True,
                )

        ghosts.append(ghost)

        if ghost.get("lat") is None:
            unresolved.append(ghost)

        if use_nominatim and index % 10 == 0:
            _set_status(
                progress=45 + 45 * index / max(total, 1),
                message=f"Nominatim: {geocoded} из ~{total}",
            )

    _set_status(progress=92, message="Сохранение артефактов…")

    places_geojson = to_geojson(matched)
    ghosts_geojson = to_geojson(ghosts)

    _write_json(PLACES_FILE, places_geojson)
    _write_json(GHOSTS_FILE, ghosts_geojson)

    with UNRESOLVED_FILE.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow([
            "уезд",
            "название",
            "альтернативное",
            "тип",
            "при",
            "жителей",
        ])

        for row in unresolved:
            population = (
                row["numbers"][-2:]
                if len(row["numbers"]) >= 2
                else []
            )
            writer.writerow([
                row["uyezd"],
                row["name"],
                row.get("alias") or "",
                row["kind"],
                row["position"],
                " + ".join(map(str, population)),
            ])

    meta = {
        "generated_at": _now(),
        "uyezds": names,
        "options": {
            "uyezd": options.get("uyezd"),
            "use_nominatim": use_nominatim,
            "skip_fetch": skip_fetch,
        },
        "counts": {
            "parsed": len(all_rows),
            "matched": len(matched),
            "ghosts": len(ghosts),
            "unresolved": len(unresolved),
            "matched_osm": len(matched),
            "matched_nominatim": sum(
                1
                for item in ghosts
                if item.get("match") == "nominatim"
            ),
        },
        "files": {
            "places": PLACES_FILE.name,
            "ghosts": GHOSTS_FILE.name,
            "unresolved": UNRESOLVED_FILE.name,
            "geocache": GEOCACHE_FILE.name,
        },
    }

    _write_json(META_FILE, meta)

    _log(
        "ГОТОВО: "
        f"НП={len(all_rows)}, совпало={len(matched)}, "
        f"привидений={len(ghosts)}, без координат={len(unresolved)}"
    )

    # Статус фиксируем и при прямом вызове (тесты, ручной прогон),
    # чтобы после перезапуска не показывать «Сохранение артефактов… 92%».
    _set_status(
        running=False,
        state="completed",
        progress=100,
        message=(
            "Готово: "
            f"совпало {len(matched)}, "
            f"привидений {len(ghosts)}, "
            f"без координат {len(unresolved)}."
        ),
        finished_at=_now(),
        error=None,
        meta=meta,
    )

    return meta


def _run_generation(options: dict) -> None:
    try:
        meta = run_generation(options)

        # Дублируем фиксацию статуса: run_generation уже пишет completed,
        # но обёртка должна закрыть прогон и при подмене/сбое внутри.
        _set_status(
            running=False,
            state="completed",
            progress=100,
            message=(
                "Готово: "
                f"совпало {meta['counts']['matched']}, "
                f"привидений {meta['counts']['ghosts']}, "
                f"без координат {meta['counts']['unresolved']}."
            ),
            finished_at=_now(),
            error=None,
            meta=meta,
        )

    except Exception as error:
        _log(f"ОШИБКА: {error}")

        _set_status(
            running=False,
            state="failed",
            message=str(error)[:1000],
            finished_at=_now(),
            error=str(error)[:2000],
        )


def start_generation(options: dict | None = None) -> dict:
    """Запустить генерацию в фоне. Вторая параллельная — 409."""

    with _LOCK:
        if _STATUS.get("running"):
            raise GenerationBusy(
                "Генерация уже выполняется. Дождитесь завершения."
            )

        _STATUS.update(
            running=True,
            state="running",
            progress=0,
            message="Задача принята.",
            started_at=_now(),
            finished_at=None,
            error=None,
        )

        _write_json(STATUS_FILE, _STATUS)

        _EXECUTOR.submit(_run_generation, dict(options or {}))

    return {"task": "accepted"}


# ──────────────────────────────────────────────────────────── чтение


def read_outputs() -> dict:
    """Прочитать готовые артефакты без пересчёта."""

    if not PLACES_FILE.is_file():
        raise FileNotFoundError(
            "Карта ещё не генерировалась: нет snm_1859_all.geojson."
        )

    places = _read_json(PLACES_FILE, _empty_collection())
    ghosts = _read_json(GHOSTS_FILE, _empty_collection())
    meta = _read_json(META_FILE, {}) or {}

    return {
        "places": places,
        "ghosts": ghosts,
        "meta": meta,
    }


def read_places() -> dict:
    if not PLACES_FILE.is_file():
        raise FileNotFoundError(
            "Карта ещё не генерировалась: нет snm_1859_all.geojson."
        )

    return _read_json(PLACES_FILE, _empty_collection())


def read_ghosts() -> dict:
    if not GHOSTS_FILE.is_file():
        raise FileNotFoundError(
            "Карта ещё не генерировалась: нет ghosts.geojson."
        )

    return _read_json(GHOSTS_FILE, _empty_collection())


def read_meta() -> dict:
    return _read_json(META_FILE, {}) or {}


# ──────────────────────────────────────────────────────────── отметки


def read_marks() -> list[dict]:
    marks = _read_json(MARKS_FILE, []) or []

    return marks if isinstance(marks, list) else []


def add_marks(payload: dict | list[dict]) -> list[dict]:
    """Добавить одну или несколько ручных отметок."""

    ensure_dirs()

    items = payload if isinstance(payload, list) else [payload]
    marks = read_marks()

    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Отметка должна быть объектом.")

        name = str(item.get("name") or "").strip()

        if not name:
            raise ValueError("У отметки должно быть имя.")

        try:
            lat = float(item.get("lat"))
            lon = float(item.get("lon"))

        except (TypeError, ValueError):
            raise ValueError("Нужны числовые lat и lon.") from None

        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("Координаты вне допустимого диапазона.")

        marks.append({
            "id": f"mark-{int(time.time() * 1000)}-{len(marks)}",
            "name": name,
            "lat": lat,
            "lon": lon,
            "note": str(item.get("note") or "").strip() or None,
            "created_at": _now(),
        })

    _write_json(MARKS_FILE, marks)

    return marks


def delete_mark(mark_id: str) -> list[dict]:
    marks = [
        mark
        for mark in read_marks()
        if mark.get("id") != mark_id
    ]

    _write_json(MARKS_FILE, marks)

    return marks


# ──────────────────────────────────────────────────────────── дороги


def _parse_bbox(value: str) -> tuple[float, float, float, float]:
    parts = [part.strip() for part in str(value).split(",")]

    if len(parts) != 4:
        raise ValueError(
            "bbox должен быть в формате west,south,east,north."
        )

    try:
        west, south, east, north = (float(part) for part in parts)

    except ValueError:
        raise ValueError("bbox должен содержать четыре числа.") from None

    if not (-180 <= west < east <= 180):
        raise ValueError("Некорректные долготы в bbox.")

    if not (-90 <= south < north <= 90):
        raise ValueError("Некорректные широты в bbox.")

    return west, south, east, north


def _overpass_to_geojson(data: dict) -> dict:
    features = []

    for element in data.get("elements") or []:
        tags = element.get("tags") or {}

        if element.get("type") == "way" and element.get("geometry"):
            coordinates = [
                [point["lon"], point["lat"]]
                for point in element["geometry"]
                if point.get("lon") is not None
                and point.get("lat") is not None
            ]

            if len(coordinates) < 2:
                continue

            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": coordinates,
                },
                "properties": {
                    "osm_id": element.get("id"),
                    "highway": tags.get("highway"),
                    "name": tags.get("name"),
                    "ref": tags.get("ref"),
                },
            })

        elif element.get("type") == "node" and tags.get("place"):
            lat = element.get("lat")
            lon = element.get("lon")

            if lat is None or lon is None:
                continue

            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [lon, lat],
                },
                "properties": {
                    "osm_id": element.get("id"),
                    "place": tags.get("place"),
                    "name": tags.get("name"),
                },
            })

    return {
        "type": "FeatureCollection",
        "features": features,
    }


def roads(bbox: str) -> dict:
    """Дороги и деревни OSM по видимому экрану (прокси Overpass)."""

    west, south, east, north = _parse_bbox(bbox)
    key = (
        round(west, 3),
        round(south, 3),
        round(east, 3),
        round(north, 3),
    )

    cached = _ROADS_CACHE.get(key)

    if cached and time.monotonic() - cached[0] < _ROADS_TTL:
        return cached[1]

    query = f"""
[out:json][timeout:60];
(
  way["highway"~"^(secondary|tertiary|unclassified)$"]
    ({south},{west},{north},{east});
  node["place"~"^(village|hamlet|town)$"]
    ({south},{west},{north},{east});
);
out geom;
"""

    payload = _overpass(query, timeout=60)
    result = _overpass_to_geojson(payload)
    result["meta"] = {
        "bbox": [west, south, east, north],
        "count": len(result["features"]),
    }

    _ROADS_CACHE[key] = (time.monotonic(), result)

    return result


__all__ = [
    "GenerationBusy",
    "GhostMapError",
    "ROOT",
    "UYEZDS",
    "add_marks",
    "delete_mark",
    "read_ghosts",
    "read_marks",
    "read_meta",
    "read_outputs",
    "read_places",
    "roads",
    "run_generation",
    "start_generation",
    "status",
]
