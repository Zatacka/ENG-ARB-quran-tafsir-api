from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _origins(raw: str) -> tuple[str, ...]:
    values = tuple(value.strip() for value in raw.split(",") if value.strip())
    return values or ("*",)


@dataclass(frozen=True, slots=True)
class Settings:
    project_root: Path
    data_dir: Path
    catalog_file: Path
    api_key: str | None
    allowed_origins: tuple[str, ...]
    cache_control: str


def load_settings() -> Settings:
    project_root = Path(__file__).resolve().parents[1]
    return Settings(
        project_root=project_root,
        data_dir=Path(os.getenv("TAFSIR_DATA_DIR", project_root / "data")).resolve(),
        catalog_file=Path(
            os.getenv("TAFSIR_CATALOG_FILE", project_root / "catalog" / "resources.json")
        ).resolve(),
        api_key=os.getenv("API_KEY") or None,
        allowed_origins=_origins(os.getenv("ALLOWED_ORIGINS", "*")),
        cache_control=os.getenv(
            "CACHE_CONTROL",
            "public, max-age=300, stale-while-revalidate=86400",
        ),
    )


settings = load_settings()
