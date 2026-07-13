from __future__ import annotations

import json
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

DB_PATH = Path("out/wic-hadith-core.sqlite3")
BASES = (
    "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1/editions",
    "https://raw.githubusercontent.com/fawazahmed0/hadith-api/1/editions",
)


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def contains_arabic(value: str) -> bool:
    return any("\u0600" <= character <= "\u06ff" for character in value)


def fetch_section(edition: str, section: str) -> str:
    quoted_edition = urllib.parse.quote(edition, safe="")
    quoted_section = urllib.parse.quote(section, safe="")
    candidates = [
        f"{base}/{quoted_edition}/sections/{quoted_section}.json"
        for base in BASES
    ] + [
        f"{base}/{quoted_edition}/sections/{quoted_section}.min.json"
        for base in BASES
    ]
    last_error: Exception | None = None
    for attempt in range(3):
        for url in candidates:
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "WIC-Hadith-Packager/2.1"})
                with urllib.request.urlopen(request, timeout=90) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                metadata = payload.get("metadata") if isinstance(payload, dict) else None
                sections = metadata.get("section") if isinstance(metadata, dict) else None
                if isinstance(sections, dict):
                    title = clean(sections.get(section) or sections.get(str(int(section))) if section.isdigit() else sections.get(section))
                    if title:
                        return title
                    for key, value in sections.items():
                        if clean(key) == section and clean(value):
                            return clean(value)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                last_error = exc
        time.sleep(2 ** attempt)
    print(f"No section title for {edition} section {section}: {last_error}")
    return ""


def main() -> None:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    pairs = connection.execute(
        """
        select distinct source_edition_en, source_edition_ar, section_number
        from hadith_references
        where section_number <> ''
        order by source_edition_en, cast(section_number as integer), section_number
        """
    ).fetchall()

    requests: dict[tuple[str, str], None] = {}
    for row in pairs:
        section = clean(row["section_number"])
        if row["source_edition_en"]:
            requests[(clean(row["source_edition_en"]), section)] = None
        if row["source_edition_ar"]:
            requests[(clean(row["source_edition_ar"]), section)] = None

    titles: dict[tuple[str, str], str] = {}
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {
            executor.submit(fetch_section, edition, section): (edition, section)
            for edition, section in requests
        }
        for future in as_completed(futures):
            key = futures[future]
            titles[key] = future.result()

    updated = 0
    for row in pairs:
        edition_en = clean(row["source_edition_en"])
        edition_ar = clean(row["source_edition_ar"])
        section = clean(row["section_number"])
        title_en = titles.get((edition_en, section), "")
        raw_ar = titles.get((edition_ar, section), "")
        title_ar = raw_ar if contains_arabic(raw_ar) else ""
        connection.execute(
            """
            update hadith_references
            set section_en = ?, section_ar = ?
            where source_edition_en = ? and source_edition_ar = ? and section_number = ?
            """,
            (title_en, title_ar, edition_en, edition_ar, section),
        )
        connection.execute(
            """
            update hadiths
            set section_en = ?
            where collection_slug in (
              select collection_slug from hadith_references
              where source_edition_en = ? and source_edition_ar = ? and section_number = ?
            ) and hadith_number in (
              select hadith_number from hadith_references
              where source_edition_en = ? and source_edition_ar = ? and section_number = ?
            )
            """,
            (title_en, edition_en, edition_ar, section, edition_en, edition_ar, section),
        )
        if title_en:
            updated += 1
    connection.execute(
        "insert or replace into package_metadata(key,value) values('section_title_count',?)",
        (str(updated),),
    )
    connection.commit()
    connection.execute("vacuum")
    connection.close()
    print(f"Enriched {updated} collection-section mappings")
    if updated < 250:
        raise RuntimeError(f"Section metadata enrichment is unexpectedly incomplete: {updated}")


if __name__ == "__main__":
    main()
