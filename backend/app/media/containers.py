"""Чтение метаданных контейнеров MP4/MOV/3GP без внешних утилит.

Извлекаются сведения, которые помогают определить место и время
съёмки: GPS-координаты, модель устройства, дата создания, XMP-теги.
ExifTool остаётся необязательным дополнением.
"""

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path


MP4_EPOCH = datetime(
    1904,
    1,
    1,
    tzinfo=timezone.utc,
)


CONTAINER_ATOMS = {
    "moov",
    "trak",
    "mdia",
    "minf",
    "stbl",
    "udta",
    "meta",
    "ilst",
    "mvex",
    "moof",
    "traf",
    "mfra",
    "edts",
    "dinf",
}


TEXT_ATOMS = {
    "\u00a9nam": "Title",
    "\u00a9day": "CreateDate",
    "\u00a9mak": "Make",
    "\u00a9mod": "Model",
    "\u00a9xyz": "GPSPosition",
    "\u00a9too": "Encoder",
    "\u00a9cmt": "Comment",
}


QUICKTIME_KEYS = {
    "com.apple.quicktime.make": "Make",
    "com.apple.quicktime.model": "Model",
    "com.apple.quicktime.creationdate": "CreateDate",
    "com.apple.quicktime.location.iso6709": "GPSPosition",
    "com.apple.quicktime.software": "Software",
}


ISO6709_PATTERN = re.compile(
    r"([+-]\d{1,3}(?:\.\d+)?)([+-]\d{1,3}(?:\.\d+)?)"
    r"(?:([+-]\d+(?:\.\d+)?))?"
)


DECIMAL_PAIR_PATTERN = re.compile(
    r"(-?\d{1,3}(?:[.,]\d+))\s*[,; ]\s*"
    r"(-?\d{1,3}(?:[.,]\d+))"
)


DMS_PATTERN = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:°|deg|d)?\s*"
    r"(\d+(?:[.,]\d+)?)\s*['\u2032]?\s*"
    r"(\d+(?:[.,]\d+)?)?\s*[\"\u2033]?\s*([NSEW])",
    re.IGNORECASE,
)


XMP_PATTERNS = {
    "Make": (
        r"(?:tiff:Make|exif:Make)=\"([^\"]+)\"",
    ),
    "Model": (
        r"(?:tiff:Model|exif:Model)=\"([^\"]+)\"",
    ),
    "CreateDate": (
        r"(?:xmp:CreateDate|exif:DateTimeOriginal)"
        r"=\"([^\"]+)\"",
    ),
    "Software": (
        r"(?:xmp:CreatorTool|exif:Software)=\"([^\"]+)\"",
    ),
    "GPSPosition": (
        r"(?:exif:GPSLatitude|exif:GPSPosition)"
        r"=\"([^\"]+)\"",
    ),
}


def read_container_metadata(path: Path) -> dict:
    """Возвращает словарь найденных тегов контейнера."""

    tags = {}

    try:
        size = path.stat().st_size

        with path.open("rb") as handle:
            for atom_type, start, end, _ in _atoms(
                handle,
                0,
                size,
            ):
                if atom_type != "moov":
                    continue

                _walk_moov(
                    handle,
                    start,
                    end,
                    tags,
                )

    except OSError:
        return tags

    tags.update(_read_xmp(path))

    return {
        key: value
        for key, value in tags.items()
        if value not in (None, "", [], {})
    }


def _atoms(handle, start: int, end: int):
    position = start

    while position + 8 <= end:
        handle.seek(position)
        header = handle.read(8)

        if len(header) < 8:
            return

        size = int.from_bytes(header[:4], "big")
        atom_type = header[4:8].decode(
            "latin-1",
            errors="replace",
        )
        header_size = 8

        if size == 1:
            extra = handle.read(8)

            if len(extra) < 8:
                return

            size = int.from_bytes(extra, "big")
            header_size = 16

        elif size == 0:
            size = end - position

        if size < header_size:
            return

        atom_end = min(end, position + size)

        yield (
            atom_type,
            position + header_size,
            atom_end,
            atom_end,
        )

        position = atom_end


def _walk_moov(
    handle,
    start: int,
    end: int,
    tags: dict,
    depth: int = 0,
) -> None:
    if depth > 6:
        return

    for atom_type, atom_start, atom_end, _ in _atoms(
        handle,
        start,
        end,
    ):
        if atom_type == "mvhd":
            created = _read_mvhd(handle, atom_start, atom_end)

            if created:
                tags.setdefault("CreateDate", created)

        elif atom_type == "loci":
            _read_loci(handle, atom_start, atom_end, tags)

        elif atom_type in TEXT_ATOMS:
            value = _read_text(handle, atom_start, atom_end)

            if value:
                tags.setdefault(
                    TEXT_ATOMS[atom_type],
                    value,
                )

        elif atom_type == "meta":
            _walk_meta(
                handle,
                atom_start + 4,
                atom_end,
                tags,
                depth + 1,
            )

        elif atom_type == "ilst":
            _read_ilst(
                handle,
                atom_start,
                atom_end,
                tags,
                {},
            )

        elif atom_type == "udta" or atom_type in CONTAINER_ATOMS:
            _walk_moov(
                handle,
                atom_start,
                atom_end,
                tags,
                depth + 1,
            )


def _walk_meta(
    handle,
    start: int,
    end: int,
    tags: dict,
    depth: int,
) -> None:
    keys = {}
    children = list(
        _atoms(handle, start, end)
    )

    for atom_type, atom_start, atom_end, _ in children:
        if atom_type == "keys":
            keys = _read_keys(
                handle,
                atom_start,
                atom_end,
            )

    for atom_type, atom_start, atom_end, _ in children:
        if atom_type == "ilst":
            _read_ilst(
                handle,
                atom_start,
                atom_end,
                tags,
                keys,
            )

        elif atom_type in ("moov", "udta"):
            _walk_moov(
                handle,
                atom_start,
                atom_end,
                tags,
                depth + 1,
            )


def _read_keys(handle, start: int, end: int) -> dict:
    data = _read_bytes(handle, start, end)
    keys = {}

    if len(data) < 8:
        return keys

    offset = 0

    if data[4:8] != b"mdta":
        offset = 4

    position = offset
    index = 1

    while position + 8 <= len(data):
        size = int.from_bytes(
            data[position:position + 4],
            "big",
        )

        if size < 8 or position + size > len(data):
            break

        namespace = data[
            position + 4:position + 8
        ]

        if namespace == b"mdta":
            key = data[
                position + 8:position + size
            ].decode("utf-8", errors="replace")

            keys[index] = key

        position += size
        index += 1

    return keys


def _read_ilst(
    handle,
    start: int,
    end: int,
    tags: dict,
    keys: dict,
) -> None:
    for atom_type, atom_start, atom_end, _ in _atoms(
        handle,
        start,
        end,
    ):
        name = TEXT_ATOMS.get(atom_type)

        if name is None and keys:
            try:
                name = QUICKTIME_KEYS.get(
                    keys.get(int.from_bytes(
                        atom_type.encode(
                            "latin-1",
                            errors="replace",
                        ),
                        "big",
                    ))
                )

            except (TypeError, ValueError):
                name = None

        if name is None:
            continue

        for child_type, child_start, child_end, _ in _atoms(
            handle,
            atom_start,
            atom_end,
        ):
            if child_type != "data":
                continue

            value = _read_data_value(
                handle,
                child_start,
                child_end,
            )

            if value in (None, "", 0):
                continue

            tags.setdefault(name, value)


def _read_data_value(handle, start: int, end: int):
    data = _read_bytes(handle, start, end)

    if len(data) <= 8:
        return None

    value_type = int.from_bytes(data[:4], "big")
    payload = data[8:]

    if value_type == 1:
        return payload.decode(
            "utf-8",
            errors="replace",
        ).strip("\x00")

    if value_type == 21:
        return int.from_bytes(
            payload[:4],
            "big",
            signed=True,
        )

    if value_type == 22:
        return int.from_bytes(
            payload[:4],
            "big",
        )

    if value_type == 23:
        import struct

        return struct.unpack(">f", payload[:4])[0]

    if value_type == 24:
        import struct

        return struct.unpack(">d", payload[:8])[0]

    return payload.decode(
        "utf-8",
        errors="replace",
    ).strip("\x00")


def _read_mvhd(handle, start: int, end: int) -> str | None:
    data = _read_bytes(handle, start, min(end, start + 32))

    if len(data) < 8:
        return None

    version = data[0]

    try:
        if version == 1:
            seconds = int.from_bytes(
                data[4:12],
                "big",
            )

        else:
            seconds = int.from_bytes(
                data[4:8],
                "big",
            )

    except ValueError:
        return None

    if seconds <= 0:
        return None

    created = MP4_EPOCH + timedelta(seconds=seconds)

    if created.year < 1990:
        return None

    return created.isoformat()


def _read_loci(
    handle,
    start: int,
    end: int,
    tags: dict,
) -> None:
    data = _read_bytes(handle, start, min(end, start + 256))

    if len(data) < 20:
        return

    position = 6

    terminator = data.find(b"\x00", position)

    if terminator < 0:
        return

    position = terminator + 1

    if position + 12 > len(data):
        return

    position += 2

    longitude = _fixed_point(data[position:position + 4])
    latitude = _fixed_point(data[position + 4:position + 8])

    if longitude is None or latitude is None:
        return

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return

    tags.setdefault(
        "GPSPosition",
        f"{latitude:.6f}{longitude:+.6f}/",
    )


def _fixed_point(raw: bytes) -> float | None:
    if len(raw) < 4:
        return None

    value = int.from_bytes(raw, "big", signed=True)

    return value / 65536.0


def _read_text(handle, start: int, end: int) -> str:
    return _read_bytes(
        handle,
        start,
        min(end, start + 4096),
    ).decode(
        "utf-8",
        errors="replace",
    ).strip("\x00").strip()


def _read_bytes(handle, start: int, end: int) -> bytes:
    handle.seek(start)

    return handle.read(max(0, end - start))


def _read_xmp(path: Path) -> dict:
    tags = {}

    try:
        size = path.stat().st_size
        chunks = []

        with path.open("rb") as handle:
            chunks.append(handle.read(1024 * 1024))

            if size > 2 * 1024 * 1024:
                handle.seek(max(0, size - 1024 * 1024))
                chunks.append(handle.read(1024 * 1024))

    except OSError:
        return tags

    text = b"\n".join(chunks).decode(
        "latin-1",
        errors="replace",
    )

    for name, patterns in XMP_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, text)

            if match:
                tags.setdefault(
                    name,
                    match.group(1).strip(),
                )
                break

    return tags


def parse_gps(tags: dict) -> list[tuple[float, float]]:
    """Возвращает координаты из тегов GPSPosition/ISO6709/XMP."""

    numeric = _numeric_gps(tags)

    if numeric is not None:
        return [numeric]

    raw = str(tags.get("GPSPosition", "")).strip()

    if not raw:
        return []

    match = ISO6709_PATTERN.search(raw)

    if match:
        latitude = float(match.group(1))
        longitude = float(match.group(2))

        if (
            -90 <= latitude <= 90
            and -180 <= longitude <= 180
        ):
            return [(latitude, longitude)]

    latitude = _parse_dms(raw, "N", "S")
    longitude = _parse_dms(raw, "E", "W")

    if latitude is None or longitude is None:
        pair = DECIMAL_PAIR_PATTERN.search(raw)

        if pair:
            latitude = float(pair.group(1).replace(",", "."))
            longitude = float(pair.group(2).replace(",", "."))

            if (
                -90 <= latitude <= 90
                and -180 <= longitude <= 180
            ):
                return [(latitude, longitude)]

        return []

    return [(latitude, longitude)]


def _numeric_gps(tags: dict) -> tuple[float, float] | None:
    """Координаты из отдельных тегов ExifTool GPSLatitude/GPSLongitude."""

    try:
        latitude = float(tags.get("GPSLatitude"))
        longitude = float(tags.get("GPSLongitude"))

    except (TypeError, ValueError):
        return None

    latitude_ref = str(tags.get("GPSLatitudeRef", "")).upper()
    longitude_ref = str(tags.get("GPSLongitudeRef", "")).upper()

    if latitude_ref.startswith("S"):
        latitude = -abs(latitude)

    if longitude_ref.startswith("W"):
        longitude = -abs(longitude)

    if not (
        -90 <= latitude <= 90
        and -180 <= longitude <= 180
    ):
        return None

    return latitude, longitude


def _parse_dms(
    text: str,
    positive: str,
    negative: str,
) -> float | None:
    for match in DMS_PATTERN.finditer(text):
        direction = match.group(4).upper()

        if direction not in (positive, negative):
            continue

        degrees = float(match.group(1).replace(",", "."))
        minutes = float(match.group(2).replace(",", "."))

        seconds = float(
            (match.group(3) or "0").replace(",", ".")
        )

        value = degrees + minutes / 60 + seconds / 3600

        return -value if direction == negative else value

    return None


def parse_iso6709(text: str) -> tuple[float, float] | None:
    match = ISO6709_PATTERN.search(str(text))

    if not match:
        return None

    latitude = float(match.group(1))
    longitude = float(match.group(2))

    if not (
        -90 <= latitude <= 90
        and -180 <= longitude <= 180
    ):
        return None

    return latitude, longitude
