from __future__ import annotations

import hmac
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    HTTPException,
    Path as ApiPath,
    Query,
    Request,
    Security,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from . import __version__
from .catalog import (
    get_language,
    get_resource,
    languages as catalog_languages,
    resources as catalog_resources,
    resources_for_language,
)
from .config import settings
from .database import (
    AyahNotFoundError,
    compare_ayah,
    database_path,
    get_passage,
    list_surah_entries,
    list_surahs,
    resolve_ayah,
    resource_summary,
    search_resource,
)
from .models import (
    CompareResponse,
    EntryListResponse,
    HealthResponse,
    LanguageListResponse,
    LanguageSummary,
    ResourceListResponse,
    ResourceSummary,
    RootResponse,
    SearchResponse,
    SurahListResponse,
    TafsirEntryResponse,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    missing = [
        str(database_path(item))
        for item in catalog_resources().values()
        if not database_path(item).is_file()
    ]
    if missing:
        preview = ", ".join(missing[:3])
        raise RuntimeError(
            f"Missing {len(missing)} tafsir database files ({preview}). "
            "Run `python scripts/prepare_data.py` before starting the API."
        )
    yield


app = FastAPI(
    title="Multilingual Quran Tafsir API",
    summary="Read, compare, and search English and Arabic Quran tafsir resources.",
    description=(
        "A read-only API over English and Arabic Quran tafsir, i'rab, gharib, "
        "qira'at, linguistic-analysis, tadabbur, and dependency-graph datasets. "
        "Grouped commentary is resolved automatically and incomplete source "
        "coverage is reported explicitly."
    ),
    version=__version__,
    lifespan=lifespan,
    license_info={
        "name": "MIT for API source code; dataset terms are separate",
    },
)

app.add_middleware(GZipMiddleware, minimum_size=700)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def response_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    if request.method == "GET" and response.status_code < 400:
        response.headers.setdefault("Cache-Control", settings.cache_control)
    return response


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(
    provided: Annotated[str | None, Security(api_key_header)],
) -> None:
    expected = settings.api_key
    if expected is None:
        return
    if provided is None or not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid X-API-Key header is required.",
        )


api = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])


def _language_or_404(code: str):
    language = get_language(code)
    if language is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "Unknown language.",
                "language": code,
                "available": list(catalog_languages()),
            },
        )
    return language


def _resource_or_404(language_code: str, slug: str):
    _language_or_404(language_code)
    definition = get_resource(language_code, slug)
    if definition is None:
        available = [item.slug for item in resources_for_language(language_code)]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "Unknown resource.",
                "language": language_code,
                "slug": slug,
                "available": available,
            },
        )
    return definition


def _entry_or_404(
    language_code: str,
    slug: str,
    surah: int,
    ayah: int,
    include_markup: bool,
):
    _resource_or_404(language_code, slug)
    try:
        return resolve_ayah(
            language_code,
            slug,
            surah,
            ayah,
            include_markup=include_markup,
        )
    except AyahNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Ayah not found.", "ayah_key": f"{surah}:{ayah}"},
        ) from None


def _resource_list_payload(language_code: str, items) -> dict[str, object]:
    language = _language_or_404(language_code)
    return {
        "language": language.public_dict(),
        "count": len(items),
        "items": [resource_summary(item) for item in items],
    }


@app.get("/", response_model=RootResponse, tags=["service"])
def root() -> dict[str, object]:
    return {
        "name": "Multilingual Quran Tafsir API",
        "version": __version__,
        "status": "ok",
        "links": {"self": "/", "docs": "/docs"},
    }


@app.get("/health", response_model=HealthResponse, tags=["service"])
def health() -> dict[str, object]:
    resources = list(catalog_resources().values())
    databases = sum(1 for item in resources if database_path(item).is_file())
    if databases != len(resources):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "error",
                "language_count": len(catalog_languages()),
                "resource_count": len(resources),
                "database_count": databases,
            },
        )
    return {
        "status": "ok",
        "language_count": len(catalog_languages()),
        "resource_count": len(resources),
        "database_count": databases,
    }


@api.get("/languages", response_model=LanguageListResponse, tags=["languages"])
def language_list() -> dict[str, object]:
    items = [item.public_dict() for item in catalog_languages().values()]
    return {"count": len(items), "items": items}


@api.get("/languages/{language_code}", response_model=LanguageSummary, tags=["languages"])
def language_detail(language_code: str) -> dict[str, object]:
    return _language_or_404(language_code).public_dict()


@api.get(
    "/languages/{language_code}/resources",
    response_model=ResourceListResponse,
    tags=["resources"],
)
def resource_list(
    language_code: str,
    q: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    resource_type: Annotated[str | None, Query(alias="type", min_length=1, max_length=40)] = None,
) -> dict[str, object]:
    _language_or_404(language_code)
    items = resources_for_language(language_code, resource_type)
    if q:
        needle = q.casefold()
        items = [
            item for item in items
            if needle in item.slug.casefold()
            or needle in item.title.casefold()
            or (item.native_title and needle in item.native_title.casefold())
        ]
    return _resource_list_payload(language_code, items)


@api.get(
    "/languages/{language_code}/tafsirs",
    response_model=ResourceListResponse,
    tags=["resources"],
)
def tafsir_list(
    language_code: str,
    q: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
) -> dict[str, object]:
    _language_or_404(language_code)
    items = resources_for_language(language_code, "tafsir")
    if q:
        needle = q.casefold()
        items = [
            item for item in items
            if needle in item.slug.casefold()
            or needle in item.title.casefold()
            or (item.native_title and needle in item.native_title.casefold())
        ]
    return _resource_list_payload(language_code, items)


@api.get(
    "/languages/{language_code}/resources/{slug}",
    response_model=ResourceSummary,
    tags=["resources"],
)
def resource_detail(language_code: str, slug: str) -> dict[str, object]:
    return resource_summary(_resource_or_404(language_code, slug))


@api.get("/surahs", response_model=SurahListResponse, tags=["surahs"])
def surahs() -> dict[str, object]:
    items = list_surahs()
    return {"count": len(items), "items": items}


@api.get(
    "/languages/{language_code}/resources/{slug}/ayahs/{surah}/{ayah}",
    response_model=TafsirEntryResponse,
    tags=["ayahs"],
)
def ayah_entry(
    language_code: str,
    slug: str,
    surah: Annotated[int, ApiPath(ge=1, le=114)],
    ayah: Annotated[int, ApiPath(ge=1, le=286)],
    include_markup: bool = False,
) -> dict[str, object]:
    return {
        "item": _entry_or_404(
            language_code,
            slug,
            surah,
            ayah,
            include_markup,
        )
    }


@api.get(
    "/languages/{language_code}/ayahs/{surah}/{ayah}/compare",
    response_model=CompareResponse,
    tags=["comparison"],
)
def compare_language(
    language_code: str,
    surah: Annotated[int, ApiPath(ge=1, le=114)],
    ayah: Annotated[int, ApiPath(ge=1, le=286)],
    resource: Annotated[list[str], Query(min_length=1)],
    include_markup: bool = False,
) -> dict[str, object]:
    _language_or_404(language_code)
    if len(resource) > 20:
        raise HTTPException(status_code=422, detail="At most 20 resources may be compared.")
    for slug in resource:
        _resource_or_404(language_code, slug)
    try:
        items = compare_ayah(
            [(language_code, slug) for slug in resource],
            surah,
            ayah,
            include_markup,
        )
    except AyahNotFoundError:
        raise HTTPException(status_code=404, detail="Ayah not found.") from None
    return {
        "ayah_key": f"{surah}:{ayah}",
        "count": len(items),
        "available_count": sum(bool(item["available"]) for item in items),
        "items": items,
    }


@api.get(
    "/ayahs/{surah}/{ayah}/compare",
    response_model=CompareResponse,
    tags=["comparison"],
)
def compare_multilingual(
    surah: Annotated[int, ApiPath(ge=1, le=114)],
    ayah: Annotated[int, ApiPath(ge=1, le=286)],
    selection: Annotated[list[str], Query(min_length=1)],
    include_markup: bool = False,
) -> dict[str, object]:
    if len(selection) > 20:
        raise HTTPException(status_code=422, detail="At most 20 resources may be compared.")
    parsed: list[tuple[str, str]] = []
    for value in selection:
        if ":" not in value:
            raise HTTPException(
                status_code=422,
                detail="Each selection must use the form language:slug, such as en:tafsir-ibn-kathir.",
            )
        language_code, slug = value.split(":", 1)
        _resource_or_404(language_code, slug)
        parsed.append((language_code, slug))
    try:
        items = compare_ayah(parsed, surah, ayah, include_markup)
    except AyahNotFoundError:
        raise HTTPException(status_code=404, detail="Ayah not found.") from None
    return {
        "ayah_key": f"{surah}:{ayah}",
        "count": len(items),
        "available_count": sum(bool(item["available"]) for item in items),
        "items": items,
    }


@api.get(
    "/languages/{language_code}/resources/{slug}/surahs/{surah}",
    response_model=EntryListResponse,
    tags=["surahs"],
)
def surah_entries(
    language_code: str,
    slug: str,
    surah: Annotated[int, ApiPath(ge=1, le=114)],
    mode: Literal["resolved", "compact"] = "resolved",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=300)] = 50,
    include_markup: bool = False,
) -> dict[str, object]:
    definition = _resource_or_404(language_code, slug)
    try:
        total, items = list_surah_entries(
            language_code,
            slug,
            surah,
            mode,
            offset,
            limit,
            include_markup,
        )
    except AyahNotFoundError:
        raise HTTPException(status_code=404, detail="Surah not found.") from None
    return {
        "resource": resource_summary(definition),
        "surah": surah,
        "mode": mode,
        "pagination": {
            "offset": offset,
            "limit": limit,
            "returned": len(items),
            "total": total,
        },
        "items": items,
    }


@api.get(
    "/languages/{language_code}/resources/{slug}/passages/{surah}/{start_ayah}/{end_ayah}",
    response_model=EntryListResponse,
    tags=["ayahs"],
)
def passage(
    language_code: str,
    slug: str,
    surah: Annotated[int, ApiPath(ge=1, le=114)],
    start_ayah: Annotated[int, ApiPath(ge=1, le=286)],
    end_ayah: Annotated[int, ApiPath(ge=1, le=286)],
    include_markup: bool = False,
) -> dict[str, object]:
    definition = _resource_or_404(language_code, slug)
    if end_ayah < start_ayah:
        raise HTTPException(status_code=422, detail="end_ayah must be at least start_ayah.")
    if end_ayah - start_ayah > 99:
        raise HTTPException(status_code=422, detail="A passage may contain at most 100 ayahs.")
    try:
        items = get_passage(
            language_code,
            slug,
            surah,
            start_ayah,
            end_ayah,
            include_markup,
        )
    except AyahNotFoundError:
        raise HTTPException(status_code=404, detail="Passage not found.") from None
    total = len(items)
    return {
        "resource": resource_summary(definition),
        "surah": surah,
        "mode": "resolved",
        "pagination": {
            "offset": 0,
            "limit": total,
            "returned": total,
            "total": total,
        },
        "items": items,
    }


@api.get(
    "/languages/{language_code}/resources/{slug}/search",
    response_model=SearchResponse,
    tags=["search"],
)
def search(
    language_code: str,
    slug: str,
    q: Annotated[str, Query(min_length=2, max_length=120)],
    surah: Annotated[int | None, Query(ge=1, le=114)] = None,
    normalize: bool | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    include_markup: bool = False,
) -> dict[str, object]:
    definition = _resource_or_404(language_code, slug)
    use_normalization = language_code.lower() == "ar" if normalize is None else normalize
    total, items = search_resource(
        language_code,
        slug,
        q.strip(),
        surah,
        offset,
        limit,
        use_normalization,
        include_markup,
    )
    return {
        "resource": resource_summary(definition),
        "query": q.strip(),
        "normalized": use_normalization,
        "surah": surah,
        "pagination": {
            "offset": offset,
            "limit": limit,
            "returned": len(items),
            "total": total,
        },
        "items": items,
    }


# Backward-compatible English aliases from the original English-only API.
@api.get("/tafsirs", response_model=ResourceListResponse, tags=["legacy"], deprecated=True)
def legacy_tafsirs(
    q: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
) -> dict[str, object]:
    return tafsir_list("en", q)


@api.get("/tafsirs/{slug}", response_model=ResourceSummary, tags=["legacy"], deprecated=True)
def legacy_tafsir(slug: str) -> dict[str, object]:
    return resource_detail("en", slug)


@api.get(
    "/tafsirs/{slug}/ayahs/{surah}/{ayah}",
    response_model=TafsirEntryResponse,
    tags=["legacy"],
    deprecated=True,
)
def legacy_ayah(
    slug: str,
    surah: Annotated[int, ApiPath(ge=1, le=114)],
    ayah: Annotated[int, ApiPath(ge=1, le=286)],
    include_markup: bool = False,
) -> dict[str, object]:
    return ayah_entry("en", slug, surah, ayah, include_markup)


@api.get(
    "/ayahs/{surah}/{ayah}/tafsirs",
    response_model=CompareResponse,
    tags=["legacy"],
    deprecated=True,
)
def legacy_compare(
    surah: Annotated[int, ApiPath(ge=1, le=114)],
    ayah: Annotated[int, ApiPath(ge=1, le=286)],
    tafsir: Annotated[list[str] | None, Query()] = None,
    include_markup: bool = False,
) -> dict[str, object]:
    slugs = tafsir or [item.slug for item in resources_for_language("en", "tafsir")]
    return compare_language("en", surah, ayah, slugs, include_markup)


@api.get(
    "/tafsirs/{slug}/surahs/{surah}",
    response_model=EntryListResponse,
    tags=["legacy"],
    deprecated=True,
)
def legacy_surah(
    slug: str,
    surah: Annotated[int, ApiPath(ge=1, le=114)],
    mode: Literal["resolved", "compact"] = "resolved",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=300)] = 50,
    include_markup: bool = False,
) -> dict[str, object]:
    return surah_entries("en", slug, surah, mode, offset, limit, include_markup)


@api.get(
    "/tafsirs/{slug}/search",
    response_model=SearchResponse,
    tags=["legacy"],
    deprecated=True,
)
def legacy_search(
    slug: str,
    q: Annotated[str, Query(min_length=2, max_length=120)],
    surah: Annotated[int | None, Query(ge=1, le=114)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    include_markup: bool = False,
) -> dict[str, object]:
    return search("en", slug, q, surah, False, offset, limit, include_markup)


app.include_router(api)
