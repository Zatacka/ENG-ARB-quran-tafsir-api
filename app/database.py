from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Iterator, Literal

from .catalog import ResourceDefinition, get_resource, resources
from .config import settings
from .content import (
    content_format,
    has_meaningful_content,
    normalize_arabic,
    to_plain_text,
)

_AYAH_KEY_RE = re.compile(r"^(\d{1,3}):(\d{1,3})$")


class UnknownResourceError(KeyError):
    pass


class AyahNotFoundError(LookupError):
    pass


def _definition(language_code: str, slug: str) -> ResourceDefinition:
    definition = get_resource(language_code, slug)
    if definition is None:
        raise UnknownResourceError(f"{language_code}:{slug}")
    return definition


def database_path(definition: ResourceDefinition) -> Path:
    return settings.data_dir / definition.database_file


@contextmanager
def connect(definition: ResourceDefinition) -> Iterator[sqlite3.Connection]:
    path = database_path(definition)
    if not path.is_file():
        raise RuntimeError(
            f"Missing database: {path}. Run `python scripts/prepare_data.py`."
        )
    connection = sqlite3.connect(str(path), timeout=20, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    try:
        yield connection
    finally:
        connection.close()


def resource_summary(definition: ResourceDefinition) -> dict[str, object]:
    return definition.public_dict()


def _parse_ayah_list(value: str | None, fallback: str) -> list[str]:
    keys = [part.strip() for part in (value or "").split(",") if part.strip()]
    return keys or [fallback]


def _fetch_row(connection: sqlite3.Connection, ayah_key: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM tafsir WHERE ayah_key = ? LIMIT 1",
        (ayah_key,),
    ).fetchone()


def _entry_from_rows(
    definition: ResourceDefinition,
    requested_key: str,
    requested_row: sqlite3.Row,
    source_row: sqlite3.Row | None,
    include_markup: bool,
) -> dict[str, object]:
    available = source_row is not None and has_meaningful_content(
        source_row["text"] or "", definition.resource_type
    )
    selected = source_row if available else requested_row
    raw = (selected["text"] or "").strip() if available else ""
    source_key = selected["ayah_key"] if available else None
    ayah_keys = _parse_ayah_list(selected["ayah_keys"], selected["ayah_key"])
    markup = raw if include_markup and content_format(raw) in {"html", "svg"} else None
    return {
        "resource": resource_summary(definition),
        "requested_ayah_key": requested_key,
        "source_ayah_key": source_key,
        "group_ayah_key": requested_row["group_ayah_key"] or requested_row["ayah_key"],
        "from_ayah_key": selected["from_ayah"] or selected["ayah_key"],
        "to_ayah_key": selected["to_ayah"] or selected["ayah_key"],
        "ayah_keys": ayah_keys,
        "is_grouped": len(ayah_keys) > 1,
        "resolved_from_group": bool(available and source_key != requested_key),
        "available": bool(available),
        "missing_reason": None if available else "resource_has_no_content_for_ayah",
        "content_format": content_format(raw) if available else definition.content_format,
        "content_text": to_plain_text(raw) if available else None,
        "content_markup": markup,
    }


def _resolve_with_connection(
    connection: sqlite3.Connection,
    definition: ResourceDefinition,
    ayah_key: str,
    include_markup: bool,
) -> dict[str, object] | None:
    requested = _fetch_row(connection, ayah_key)
    if requested is None:
        return None

    if has_meaningful_content(requested["text"] or "", definition.resource_type):
        source = requested
    else:
        group_key = (requested["group_ayah_key"] or "").strip()
        source = _fetch_row(connection, group_key) if group_key else None
        if source is not None and not has_meaningful_content(
            source["text"] or "", definition.resource_type
        ):
            source = None
    return _entry_from_rows(
        definition,
        ayah_key,
        requested,
        source,
        include_markup,
    )


def resolve_ayah(
    language_code: str,
    slug: str,
    surah: int,
    ayah: int,
    include_markup: bool = True,
) -> dict[str, object]:
    definition = _definition(language_code, slug)
    key = f"{surah}:{ayah}"
    with connect(definition) as connection:
        entry = _resolve_with_connection(connection, definition, key, include_markup)
    if entry is None:
        raise AyahNotFoundError(key)
    return entry


@lru_cache(maxsize=1)
def list_surahs() -> list[dict[str, int]]:
    definition = next(iter(resources().values()))
    with connect(definition) as connection:
        rows = connection.execute(
            """
            SELECT
                CAST(substr(ayah_key, 1, instr(ayah_key, ':') - 1) AS INTEGER) AS surah,
                COUNT(DISTINCT ayah_key) AS ayah_count
            FROM tafsir
            GROUP BY surah
            ORDER BY surah
            """
        ).fetchall()
    return [
        {"surah": int(row["surah"]), "ayah_count": int(row["ayah_count"])}
        for row in rows
    ]


def list_surah_entries(
    language_code: str,
    slug: str,
    surah: int,
    mode: Literal["resolved", "compact"],
    offset: int,
    limit: int,
    include_markup: bool,
) -> tuple[int, list[dict[str, object]]]:
    definition = _definition(language_code, slug)
    pattern = f"{surah}:%"
    with connect(definition) as connection:
        rows = connection.execute(
            """
            SELECT * FROM tafsir
            WHERE ayah_key LIKE ?
            ORDER BY CAST(substr(ayah_key, instr(ayah_key, ':') + 1) AS INTEGER)
            """,
            (pattern,),
        ).fetchall()
        if not rows:
            raise AyahNotFoundError(f"surah {surah}")

        if mode == "compact":
            selected = [
                row for row in rows
                if has_meaningful_content(row["text"] or "", definition.resource_type)
            ]
        else:
            selected = rows
        total = len(selected)
        items = []
        for row in selected[offset : offset + limit]:
            entry = _resolve_with_connection(
                connection,
                definition,
                row["ayah_key"],
                include_markup,
            )
            if entry is not None:
                items.append(entry)
    return total, items


def get_passage(
    language_code: str,
    slug: str,
    surah: int,
    start_ayah: int,
    end_ayah: int,
    include_markup: bool,
) -> list[dict[str, object]]:
    definition = _definition(language_code, slug)
    with connect(definition) as connection:
        rows = connection.execute(
            """
            SELECT * FROM tafsir
            WHERE CAST(substr(ayah_key, 1, instr(ayah_key, ':') - 1) AS INTEGER) = ?
              AND CAST(substr(ayah_key, instr(ayah_key, ':') + 1) AS INTEGER)
                  BETWEEN ? AND ?
            ORDER BY CAST(substr(ayah_key, instr(ayah_key, ':') + 1) AS INTEGER)
            """,
            (surah, start_ayah, end_ayah),
        ).fetchall()
        items = [
            entry
            for row in rows
            if (
                entry := _resolve_with_connection(
                    connection,
                    definition,
                    row["ayah_key"],
                    include_markup,
                )
            ) is not None
        ]
    if not items:
        raise AyahNotFoundError(f"{surah}:{start_ayah}-{end_ayah}")
    return items


def compare_ayah(
    selections: list[tuple[str, str]],
    surah: int,
    ayah: int,
    include_markup: bool,
) -> list[dict[str, object]]:
    return [
        resolve_ayah(language, slug, surah, ayah, include_markup)
        for language, slug in selections
    ]


def _excerpt(text: str, query: str, normalized: bool, radius: int = 160) -> str:
    haystack = normalize_arabic(text) if normalized else text.casefold()
    needle = normalize_arabic(query) if normalized else query.casefold()
    index = haystack.find(needle)
    if index < 0:
        return text[: radius * 2].strip()
    # Normalized Arabic may have a slightly different index. A nearby excerpt is sufficient.
    start = max(0, index - radius)
    end = min(len(text), index + len(query) + radius)
    result = text[start:end].strip()
    if start > 0:
        result = "…" + result
    if end < len(text):
        result += "…"
    return result


def search_resource(
    language_code: str,
    slug: str,
    query: str,
    surah: int | None,
    offset: int,
    limit: int,
    normalize: bool,
    include_markup: bool,
) -> tuple[int, list[dict[str, object]]]:
    definition = _definition(language_code, slug)
    with connect(definition) as connection:
        if surah is None:
            rows = connection.execute(
                "SELECT * FROM tafsir ORDER BY rowid"
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT * FROM tafsir
                WHERE ayah_key LIKE ?
                ORDER BY CAST(substr(ayah_key, instr(ayah_key, ':') + 1) AS INTEGER)
                """,
                (f"{surah}:%",),
            ).fetchall()

        needle = normalize_arabic(query) if normalize else query.casefold()
        matches: list[tuple[sqlite3.Row, str]] = []
        for row in rows:
            raw = row["text"] or ""
            if not has_meaningful_content(raw, definition.resource_type):
                continue
            text = to_plain_text(raw)
            haystack = normalize_arabic(text) if normalize else text.casefold()
            if needle in haystack:
                matches.append((row, text))

        total = len(matches)
        items = []
        for row, text in matches[offset : offset + limit]:
            entry = _entry_from_rows(
                definition,
                row["ayah_key"],
                row,
                row,
                include_markup,
            )
            items.append(
                {
                    "entry": entry,
                    "excerpt": _excerpt(text, query, normalize),
                }
            )
    return total, items
