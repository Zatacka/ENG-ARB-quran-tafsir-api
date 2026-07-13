from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from functools import lru_cache

from .config import settings


@dataclass(frozen=True, slots=True)
class LanguageDefinition:
    code: str
    name: str
    native_name: str
    resource_count: int
    tafsir_count: int
    resource_types: tuple[str, ...]

    def public_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["resource_types"] = list(self.resource_types)
        return data


@dataclass(frozen=True, slots=True)
class ResourceDefinition:
    language_code: str
    language: str
    slug: str
    title: str
    native_title: str | None
    resource_type: str
    database_file: str
    source_file: str
    original_row_count: int
    duplicate_rows_removed: int
    ayah_count: int
    source_entries: int
    grouped_ayahs: int
    available_ayahs: int
    missing_ayahs: int
    content_format: str

    def public_dict(self) -> dict[str, object]:
        data = asdict(self)
        data.pop("database_file")
        return data


@lru_cache(maxsize=1)
def _load() -> tuple[
    dict[str, LanguageDefinition],
    dict[tuple[str, str], ResourceDefinition],
]:
    payload = json.loads(settings.catalog_file.read_text(encoding="utf-8"))
    languages = {
        item["code"]: LanguageDefinition(
            code=item["code"],
            name=item["name"],
            native_name=item["native_name"],
            resource_count=int(item["resource_count"]),
            tafsir_count=int(item["tafsir_count"]),
            resource_types=tuple(item["resource_types"]),
        )
        for item in payload["languages"]
    }
    resources = {}
    for item in payload["resources"]:
        definition = ResourceDefinition(**item)
        resources[(definition.language_code, definition.slug)] = definition
    return languages, resources


def languages() -> dict[str, LanguageDefinition]:
    return _load()[0]


def resources() -> dict[tuple[str, str], ResourceDefinition]:
    return _load()[1]


def get_language(code: str) -> LanguageDefinition | None:
    return languages().get(code.lower())


def get_resource(language_code: str, slug: str) -> ResourceDefinition | None:
    return resources().get((language_code.lower(), slug))


def resources_for_language(
    language_code: str,
    resource_type: str | None = None,
) -> list[ResourceDefinition]:
    items = [
        item
        for (code, _), item in resources().items()
        if code == language_code.lower()
        and (resource_type is None or item.resource_type == resource_type)
    ]
    return sorted(items, key=lambda item: item.title.casefold())
