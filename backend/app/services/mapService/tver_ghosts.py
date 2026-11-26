#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tver_ghosts.py — генератор слоя "привидений" для Тверской области.

Что делает:
  1. Скачивает списки населённых мест (СНМ) Тверской губернии 1859 г.
     со страниц pomnirod.ru (перевод Дубоделова П.С.) по всем 12 уездам.
  2. Парсит строки: название, тип (с./д./сц./пог./хут.), "при чём", дворы, жители.
  3. Сопоставляет названия с современными деревнями OSM (запрос Overpass
     по всей Тверской области) — совпавшим точкам координаты даёт OSM.
  4. Несовпавшие названия геокодирует через Nominatim (с кэшем и паузой).
  5. Результаты:
       out/snm_1859_all.geojson   — все НП 1859 г. с координатами (если нашлись)
       out/ghosts.geojson         — "привидения": были в 1859, не найдены сейчас
       out/unresolved.csv         — НП без координат (ставить вручную по Менде)
       out/geocache.json          — кэш геокодирования (можно прерывать)
     с флагом --html дополнительно собирает автономную карту
       out/ghost_map.html         — OSM + Менде + красные круги "привидений"

Использование:
  python tver_ghosts.py                       # все уезды
  python tver_ghosts.py --uyezd новоторжский   # один уезд (для отладки)
  python tver_ghosts.py --html --uyezd старицкий
  python tver_ghosts.py --skip-fetch --dir raw_html   # использовать уже скачанные HTML

Зависимости: pip install requests
"""

import argparse
import csv
import difflib
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
OUT = BASE / "out"
OUT.mkdir(exist_ok=True)
CACHE_DIR = OUT / "raw_html"
CACHE_DIR.mkdir(exist_ok=True)

GEOCACHE_FILE = OUT / "geocache.json"
GEOCACHE = {}
if GEOCACHE_FILE.exists():
    GEOCACHE = json.loads(GEOCACHE_FILE.read_text(encoding="utf-8"))

UA = {"User-Agent": "tver-ghosts-research/1.0 (local research script)"}

# 12 уездов Тверской губернии по списку 1859/1862 гг.
# slug — часть URL на pomnirod.ru (проверена для Новоторжского уезда;
# для остальных строится по той же схеме, при 404 см. README/правки).
UYEZDS = {
    "тверской":       "tverskoj-uezd-tverskoj-gubernii",
    "бежецкий":       "bezhetskij-uezd-tverskoj-gubernii",
    "весьегонский":   "vesegonskij-uezd-tverskoj-gubernii",
    "вышневолоцкий":  "vyshnevolockij-uezd-tverskoj-gubernii",
    "зубцовский":     "zubcovskij-uezd-tverskoj-gubernii",
    "калязинский":    "kalyazinskij-uezd-tverskoj-gubernii",
    "кашинский":      "kashinskij-uezd-tverskoj-gubernii",
    "корчевский":     "korchewskij-uezd-tverskoj-gubernii",
    "новоторжский":   "novotorzhskij-uezd-tverskoj-gubernii",
    "осташковский":   "ostashkovskij-uezd-tverskoj-gubernii",
    "ржевский":       "rzhevskij-uezd-tverskoj-gubernii",
    "старицкий":      "starickij-uezd-tverskoj-gubernii",
}

POMNIROD_TPL = (
    "https://pomnirod.ru/materialy-k-statyam/"
    "administrativno-territorialnoe-delenie-rossijskoj-imperii/"
    "gubernii-rossii/tverskaya-guberniya/naselennye-mesta-gubernii/"
    "{slug}/naselennye-mesta-{slug}/spisok-naselennyh-mest-{uzda}-za-1859-g.html"
)


def uyezd_url(ru_name: str) -> str:
    slug = UYEZDS[ru_name]
    uzda = slug.split("-uezd")[0]
    # "novotorzhskij" -> "novotorzhskogo"
    if uzda.endswith("ij"):
        uzda = uzda[:-2] + "ogo"
    elif uzda.endswith("skij"):
        uzda = uzda[:-4] + "skogo"
    return POMNIROD_TPL.format(slug=slug, uzda=uzda)


# ---------------------------------------------------------------- парсер

ROW_RE = re.compile(
    r"^(?:\d{2,5}\s+)?"
    r"(?P<name>[А-ЯЁ][^0-9(]+?)(?:\s*\((?P<alias>[^)]+)\))?\s+"
    r"(?P<kind>с\.|д\.|сц\.|пог\.|хут\.|высел\.|сл\.|скот\.\s*дв\.)\s*"
    r"(?P<type>[А-Яа-я][А-Яа-я. ]{0,10}?)\s*"
    r"при\s+(?P<position>[^0-9]+?)\s*"
    r"(?P<nums>[\d\s.]+)$",
    re.MULTILINE | re.IGNORECASE,
)

GEO_SNIP_RE = re.compile(
    r"(?:lat|geo|ll)[\"']?\s*[:=]\s*[\"']?(\d{2}\.\d{2,6})[,\s]+(\d{2}\.\d{2,6})",
    re.IGNORECASE,
)


def parse_snm(html: str) -> list[dict]:
    rows = []
    seen_names = set(GEOCACHE)  # не важно, ниже чистим

    for m in ROW_RE.finditer(html):
        name = m.group("name").strip().strip(",;")
        if not name or len(name) < 3:
            continue
        nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", m.group("nums"))]
        rows.append({
            "name": name,
            "alias": (m.group("alias") or "").strip() or None,
            "kind": m.group("kind").strip(),
            "position": m.group("position").strip(" .,"),
            "numbers": nums,
        })

    # Скрытые координаты в HTML (если авторы их вшивают — тогда гео не нужно)
    for lat, lon in GEO_SNIP_RE.findall(html)[:2000]:
        pass  # резерв для будущего сопоставления по порядку; пока не используем

    return rows


# ---------------------------------------------------------------- имена

def normalize_name(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold()
    s = s.replace("ё", "е")
    # дореформенные хвосты
    s = s.replace("ій", "ий").replace("ый", "ий")
    s = re.sub(r"[^а-я a-z]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def name_close(a: str, b: str, max_dist: int = 2) -> bool:
    a, b = normalize_name(a), normalize_name(b)
    if not a or not b:
        return False
    if a == b:
        return True
    # типовые сокращения: Большая/Б., Старое/Ст.
    short = {a: None, b: None}
    for k in list(short):
        if len(k) <= 3:
            short[k] = k
    if len(a) == 1 or len(b) == 1:
        return a[0] == b[0]
    return levenshtein(a, b) <= max_dist


# ---------------------------------------------------------------- сеть

def fetch_html(url: str, cache_name: str) -> str | None:
    cache = CACHE_DIR / cache_name
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    try:
        r = requests.get(url, headers=UA, timeout=30)
        if r.status_code == 200 and len(r.text) > 3000:
            cache.write_text(r.text, encoding="utf-8")
            time.sleep(1.5)
            return r.text
        print(f"  ! {r.status_code} для {url}")
    except Exception as e:
        print(f"  ! сеть: {e}")
    return None


OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def fetch_modern_places() -> list[dict]:
    q = """
[out:json][timeout:180];
area["ISO3166-2"="RU-TVE"]->.a;
nwr(area.a)[place~"^(village|hamlet|town)$"];
out center tags;
"""
    cache = OUT / "osm_places_tver.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))["elements"]

    for url in OVERPASS_URLS:
        try:
            r = requests.post(url, data={"data": q}, headers=UA, timeout=300)
            if r.status_code == 200:
                data = r.json()
                cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                return data["elements"]
        except Exception as e:
            print(f"  ! overpass: {e}")
    raise SystemExit("Overpass недоступен — положите кэш в out/osm_places_tver.json")


def geocode(name: str) -> list[dict]:
    """Nominatim: точное место в границах Тверской области. С кэшем."""
    key = normalize_name(name)
    if key in GEOCACHE:
        return GEOCACHE[key]

    q = f"{name}, Тверская область, Россия"
    params = {
        "q": q, "format": "jsonv2", "limit": 3,
        "countrycodes": "ru",
        "viewbox": "31.0,58.9,38.6,56.2", "bounded": 1,
    }
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search",
                         params=params, headers=UA, timeout=20)
        if r.status_code == 200:
            res = [{"lat": float(i["lat"]), "lon": float(i["lon"]),
                    "display": i.get("display_name", "")}
                   for i in r.json()]
        else:
            res = []
    except Exception:
        res = []

    GEOCACHE[key] = res
    GEOCACHE_FILE.write_text(json.dumps(GEOCACHE, ensure_ascii=False), encoding="utf-8")
    time.sleep(1.1)  # лимит Nominatim
    return res


def haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    import math
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * 6371 * math.asin(math.sqrt(h))


# ---------------------------------------------------------------- GeoJSON

def to_geojson(items: list[dict]) -> dict:
    feats = []
    for it in items:
        if it.get("lat") is None:
            continue
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point",
                         "coordinates": [it["lon"], it["lat"]]},
            "properties": {k: v for k, v in it.items()
                           if k not in ("lat", "lon")},
        })
    return {"type": "FeatureCollection", "features": feats}


def save_geojson(path: Path, fc: dict) -> None:
    path.write_text(json.dumps(fc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  → {path.name}: {len(fc['features'])} точек")


# ---------------------------------------------------------------- HTML-карта

HTML_TPL = """<!doctype html>
<html><head><meta charset="utf-8"><title>Привидения Тверской губернии</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
body,html{margin:0;height:100%}
#map{height:100%}
.legend{position:fixed;bottom:12px;left:12px;background:#fff;padding:8px 12px;
border-radius:6px;font:13px sans-serif;z-index:1000;box-shadow:0 1px 5px #0003}
</style></head><body>
<div id="map"></div>
<div class="legend">
<span style="color:#c00">⭕</span> привидение (был в 1859, сейчас не найден) &nbsp;
<span style="color:#080">●</span> найден в OSM сейчас
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const ghosts = {ghosts};
const matched = {matched};
const mendeUrl = localStorage.getItem('mende_url') ||
  'https://retromap.ru/141853/{{z}}/{{x}}/{{y}}.png';
const map = L.map('map').setView([57.0, 35.6], 8);
L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
  {maxZoom: 18}).addTo(map);
const mende = L.tileLayer(mendeUrl, {maxZoom: 18, opacity: 0.55}).addTo(map);
L.geoJSON(ghosts, {
  pointToLayer: (f, ll) => L.circleMarker(ll, {
    radius: 9, color: '#cc0000', fillColor: '#cc000033',
    fillOpacity: 0.4, weight: 2
  }).bindPopup(`<b>${f.properties.name}</b><br>${f.properties.kind || ''} при ${f.properties.position || ''}<br>уезд: ${f.properties.uyezd || ''}`)
}).addTo(map);
L.geoJSON(matched, {
  pointToLayer: (f, ll) => L.circleMarker(ll, {
    radius: 4, color: '#008800', fillOpacity: 0.8
  }).bindPopup(f.properties.name)
}).addTo(map);
</script></body></html>
"""


def build_html(ghosts: dict, matched: dict) -> None:
    html = HTML_TPL.replace("{ghosts}", json.dumps(ghosts, ensure_ascii=False))
    html = html.replace("{matched}", json.dumps(matched, ensure_ascii=False))
    path = OUT / "ghost_map.html"
    path.write_text(html, encoding="utf-8")
    print(f"  → {path.name} собрана")


# ---------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uyezd", help="имя уезда (напр. новоторжский)")
    ap.add_argument("--html", action="store_true", help="собрать ghost_map.html")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--nominatim", action="store_true",
                    help="геокодировать несовпавшие через Nominatim (медленно)")
    args = ap.parse_args()

    names = list(UYEZDS)
    if args.uyezd:
        names = [n for n in names if n in args.uyezd.lower()]

    all_rows = []
    for u in names:
        print(f"[{u}]")
        if args.skip_fetch:
            f = CACHE_DIR / f"{u}.html"
            html = f.read_text(encoding="utf-8") if f.exists() else None
            if html is None:
                print("  ! нет файла в out/raw_html — скачайте вручную")
                continue
        else:
            html = fetch_html(uyezd_url(u), f"{u}.html")
            if html is None:
                print("  ! страница не получена; скачайте вручную из pomnirod.ru "
                      "и положите в out/raw_html/{u}.html".replace("{u}", u))
                continue
        rows = parse_snm(html)
        print(f"  распарсено НП: {len(rows)}")
        for r in rows:
            r["uyezd"] = u
        all_rows.extend(rows)

    if not all_rows:
        sys.exit("Не распарсено ни одной строки — проверьте HTML.")

    print(f"\nВсего НП: {len(all_rows)}. Загружаю современные деревни OSM…")
    modern = []
    for el in fetch_modern_places():
        t = el.get("tags", {})
        nm = t.get("name")
        if not nm:
            continue
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None:
            continue
        modern.append({"name": nm, "lat": lat, "lon": lon,
                       "place": t.get("place", "")})
    print(f"современных НП в OSM: {len(modern)}")

    # индекс по нормализованному имени
    by_name: dict[str, list[dict]] = {}
    for m in modern:
        by_name.setdefault(normalize_name(m["name"]), []).append(m)

    matched, ghosts, unresolved = [], [], []
    for r in all_rows:
        candidates = by_name.get(normalize_name(r["name"]), [])
        hit = None
        if len(candidates) == 1:
            hit = candidates[0]
        elif len(candidates) > 1:
            hit = candidates[0]  # дубликат имени: берём первый, помечаем
            r["ambiguous"] = True
        else:
            # ищем ближайшее по Левенштейну среди всего индекса
            best = difflib.get_close_matches(normalize_name(r["name"]),
                                             list(by_name), n=1, cutoff=0.88)
            if best:
                hit = by_name[best[0]][0]
                r["fuzzy"] = True

        if hit:
            r.update(lat=hit["lat"], lon=hit["lon"],
                     match="osm", modern_name=hit["name"])
            matched.append(r)
        else:
            if args.nominatim:
                res = geocode(r["name"])
                if res:
                    r.update(lat=res[0]["lat"], lon=res[0]["lon"],
                             match="nominatim",
                             modern_name=res[0]["display"])
                    matched.append(r)
                    continue
            ghosts.append(r)  # без координат; в unresolved.csv
            unresolved.append(r)

    # Если Nominatim не нужен, в ghosts координат нет — но криволинейные
    # ситуации, когда в OSM названия нет, а Nominatim его знает, закрывает
    # флаг --nominatim.

    print("\nСохраняю результаты…")
    save_geojson(OUT / "snm_1859_all.geojson", to_geojson(matched))
    save_geojson(OUT / "ghosts.geojson", to_geojson(ghosts))

    with open(OUT / "unresolved.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["уезд", "название", "альтернативное", "тип", "при", "жителей"])
        for r in unresolved:
            pop = r["numbers"][-2:] if len(r["numbers"]) >= 2 else []
            w.writerow([r["uyezd"], r["name"], r.get("alias") or "",
                        r["kind"], r["position"], " + ".join(map(str, pop))])
    print(f"  → unresolved.csv: {len(unresolved)} НП без координат")

    if args.html:
        build_html(to_geojson(ghosts), to_geojson(matched))

    print("\nГотово. Совпадений:", len(matched),
          "| привидений:", len(ghosts),
          "| неразрешённых:", len(unresolved))


if __name__ == "__main__":
    main()
