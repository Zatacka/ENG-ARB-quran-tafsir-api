from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class LinkSet(BaseModel):
    self: str
    docs: str | None = None


class RootResponse(BaseModel):
    name: str
    version: str
    status: str
    links: LinkSet


class HealthResponse(BaseModel):
    status: Literal["ok"]
    language_count: int
    resource_count: int
    database_count: int


class LanguageSummary(BaseModel):
    code: str
    name: str
    native_name: str
    resource_count: int
    tafsir_count: int
    resource_types: list[str]


class LanguageListResponse(BaseModel):
    count: int
    items: list[LanguageSummary]


class ResourceSummary(BaseModel):
    language_code: str
    language: str
    slug: str
    title: str
    native_title: str | None
    resource_type: str
    source_file: str
    original_row_count: int
    duplicate_rows_removed: int
    ayah_count: int
    source_entries: int
    grouped_ayahs: int
    available_ayahs: int
    missing_ayahs: int
    content_format: str


class ResourceListResponse(BaseModel):
    language: LanguageSummary
    count: int
    items: list[ResourceSummary]


class SurahSummary(BaseModel):
    surah: int
    ayah_count: int


class SurahListResponse(BaseModel):
    count: int
    items: list[SurahSummary]


class TafsirEntry(BaseModel):
    resource: ResourceSummary
    requested_ayah_key: str
    source_ayah_key: str | None
    group_ayah_key: str
    from_ayah_key: str
    to_ayah_key: str
    ayah_keys: list[str]
    is_grouped: bool
    resolved_from_group: bool
    available: bool
    missing_reason: str | None
    content_format: str
    content_text: str | None
    content_markup: str | None


class TafsirEntryResponse(BaseModel):
    item: TafsirEntry


class CompareResponse(BaseModel):
    ayah_key: str
    count: int
    available_count: int
    items: list[TafsirEntry]


class Pagination(BaseModel):
    offset: int
    limit: int
    returned: int
    total: int


class EntryListResponse(BaseModel):
    resource: ResourceSummary
    surah: int
    mode: Literal["resolved", "compact"]
    pagination: Pagination
    items: list[TafsirEntry]


class SearchResult(BaseModel):
    entry: TafsirEntry
    excerpt: str


class SearchResponse(BaseModel):
    resource: ResourceSummary
    query: str
    normalized: bool
    surah: int | None
    pagination: Pagination
    items: list[SearchResult]
