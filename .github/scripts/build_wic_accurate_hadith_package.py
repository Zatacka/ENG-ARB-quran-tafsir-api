from __future__ import annotations

import json
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROVIDER_NAME = "Hadith API by Fawaz Ahmed"
PROVIDER_REPOSITORY = "https://github.com/fawazahmed0/hadith-api"
PROVIDER_VERSION = "1"

COLLECTIONS = [
    {
        "slug": "bukhari", "name_en": "Sahih al-Bukhari", "name_ar": "صحيح البخاري",
        "compiler_en": "Imam Muhammad al-Bukhari", "classification": "sahih",
        "authenticity_en": "A primary canonical collection whose compiler intended to include authentic reports under his conditions.",
        "edition_en": "eng-bukhari", "edition_ar": "ara-bukhari",
    },
    {
        "slug": "muslim", "name_en": "Sahih Muslim", "name_ar": "صحيح مسلم",
        "compiler_en": "Imam Muslim ibn al-Hajjaj", "classification": "sahih",
        "authenticity_en": "A primary canonical collection whose compiler intended to include authentic reports under his conditions.",
        "edition_en": "eng-muslim", "edition_ar": "ara-muslim",
    },
    {
        "slug": "abudawud", "name_en": "Sunan Abi Dawud", "name_ar": "سنن أبي داود",
        "compiler_en": "Imam Abu Dawud al-Sijistani", "classification": "sunan",
        "authenticity_en": "A major Sunan collection containing reports of differing grades. Use the displayed grading and specialist scholarship.",
        "edition_en": "eng-abudawud", "edition_ar": "ara-abudawud",
    },
    {
        "slug": "tirmidhi", "name_en": "Jami at-Tirmidhi", "name_ar": "جامع الترمذي",
        "compiler_en": "Imam Muhammad at-Tirmidhi", "classification": "sunan",
        "authenticity_en": "A major collection that records scholarly grading and legal discussion; reports have differing grades.",
        "edition_en": "eng-tirmidhi", "edition_ar": "ara-tirmidhi",
    },
    {
        "slug": "nasai", "name_en": "Sunan an-Nasa'i", "name_ar": "سنن النسائي",
        "compiler_en": "Imam Ahmad an-Nasa'i", "classification": "sunan",
        "authenticity_en": "A major Sunan collection containing reports of differing grades. Use the displayed grading and specialist scholarship.",
        "edition_en": "eng-nasai", "edition_ar": "ara-nasai",
    },
    {
        "slug": "ibnmajah", "name_en": "Sunan Ibn Majah", "name_ar": "سنن ابن ماجه",
        "compiler_en": "Imam Ibn Majah al-Qazwini", "classification": "sunan",
        "authenticity_en": "A major Sunan collection containing reports of differing grades. Use the displayed grading and specialist scholarship.",
        "edition_en": "eng-ibnmajah", "edition_ar": "ara-ibnmajah",
    },
    {
        "slug": "malik", "name_en": "Muwatta Malik", "name_ar": "موطأ مالك",
        "compiler_en": "Imam Malik ibn Anas", "classification": "muwatta",
        "authenticity_en": "An early hadith and legal collection containing marfu, mawquf and other reports with scholarly transmission context.",
        "edition_en": "eng-malik", "edition_ar": "ara-malik",
    },
    {
        "slug": "nawawi", "name_en": "Forty Hadith of an-Nawawi", "name_ar": "الأربعون النووية",
        "compiler_en": "Imam Yahya an-Nawawi", "classification": "curated",
        "authenticity_en": "A foundational curated collection of comprehensive hadiths selected by Imam an-Nawawi.",
        "edition_en": "eng-nawawi", "edition_ar": "ara-nawawi",
    },
    {
        "slug": "qudsi", "name_en": "Forty Hadith Qudsi", "name_ar": "الأربعون القدسية",
        "compiler_en": "Curated collection", "classification": "curated",
        "authenticity_en": "A thematic curated collection. Individual source references and grades should be consulted.",
        "edition_en": "eng-qudsi", "edition_ar": "ara-qudsi",
    },
    {
        "slug": "dehlawi", "name_en": "Forty Hadith Shah Waliullah Dehlawi", "name_ar": "الأربعون للدهلوي",
        "compiler_en": "Shah Waliullah Dehlawi", "classification": "curated",
        "authenticity_en": "A curated forty-hadith collection. Individual source references and grades should be consulted.",
        "edition_en": "eng-dehlawi", "edition_ar": "ara-dehlawi",
    },
]


def text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def has_arabic(value: str) -> bool:
    return any("\u0600" <= character <= "\u06ff" for character in value)


def fetch_json(edition: str) -> dict:
    candidates = []
    for filename in (f"{edition}.min.json", f"{edition}.json"):
        candidates.extend([
            f"https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1/editions/{filename}",
            f"https://raw.githubusercontent.com/fawazahmed0/hadith-api/1/editions/{filename}",
        ])
    last_error: Exception | None = None
    for attempt in range(3):
        for url in candidates:
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "WIC-Hadith-Packager/2.0"})
                with urllib.request.urlopen(request, timeout=180) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if isinstance(payload, dict) and isinstance(payload.get("hadiths"), list):
                    print(f"Downloaded {edition}: {len(payload['hadiths'])} records from {url}")
                    return payload
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                last_error = exc
        time.sleep(2 ** attempt)
    raise RuntimeError(f"Could not download {edition}: {last_error}")


def metadata_sections(payload: dict) -> dict[str, str]:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    sections = metadata.get("section") if isinstance(metadata.get("section"), dict) else {}
    return {text(key): text(value) for key, value in sections.items() if text(key)}


def grade_rows(*values: object) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for value in values:
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            name = text(item.get("name"))
            grade = text(item.get("grade"))
            if not name and not grade:
                continue
            key = (name.casefold(), grade.casefold())
            if key in seen:
                continue
            seen.add(key)
            result.append({"name": name, "grade": grade})
    return result


def exact_source_url(edition: str, number: str) -> str:
    return (
        "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1/editions/"
        f"{urllib.parse.quote(edition, safe='')}/{urllib.parse.quote(number, safe='')}.json"
    )


def build() -> Path:
    output = Path("out/wic-hadith-core.sqlite3")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    connection = sqlite3.connect(output)
    connection.execute("pragma journal_mode=off")
    connection.execute("pragma synchronous=off")
    connection.executescript(
        """
        create table collections(
          slug text primary key,
          name_en text not null,
          name_ar text not null default '',
          compiler_en text not null default '',
          classification text not null default '',
          authenticity_en text not null default '',
          cover_path text not null default '',
          edition_en text not null default '',
          edition_ar text not null default ''
        );
        create table hadiths(
          id integer primary key,
          collection_slug text not null,
          hadith_number text not null,
          section_en text not null default '',
          arabic_text text not null default '',
          translation_en text not null default '',
          grades_json text not null default '[]',
          source_url text not null default '',
          unique(collection_slug, hadith_number)
        );
        create table hadith_references(
          id integer primary key,
          collection_slug text not null,
          hadith_number text not null,
          arabic_number text not null default '',
          section_number text not null default '',
          section_en text not null default '',
          section_ar text not null default '',
          book_number text not null default '',
          in_book_hadith text not null default '',
          source_edition_en text not null default '',
          source_edition_ar text not null default '',
          provider_name text not null default '',
          provider_url text not null default '',
          unique(collection_slug, hadith_number)
        );
        create table package_metadata(key text primary key, value text not null);
        create index ix_hadith_collection on hadiths(collection_slug);
        create index ix_hadith_reference_collection on hadith_references(collection_slug);
        """
    )
    total = 0
    graded = 0
    for collection in COLLECTIONS:
        english = fetch_json(collection["edition_en"])
        arabic = fetch_json(collection["edition_ar"])
        english_sections = metadata_sections(english)
        arabic_sections = metadata_sections(arabic)
        arabic_by_hadith: dict[str, dict] = {}
        arabic_by_number: dict[str, dict] = {}
        for row in arabic.get("hadiths", []):
            if not isinstance(row, dict):
                continue
            hadith_number = text(row.get("hadithnumber"))
            arabic_number = text(row.get("arabicnumber"))
            if hadith_number and hadith_number not in arabic_by_hadith:
                arabic_by_hadith[hadith_number] = row
            if arabic_number and arabic_number not in arabic_by_number:
                arabic_by_number[arabic_number] = row

        connection.execute(
            "insert into collections(slug,name_en,name_ar,compiler_en,classification,authenticity_en,edition_en,edition_ar) values(?,?,?,?,?,?,?,?)",
            (
                collection["slug"], collection["name_en"], collection["name_ar"],
                collection["compiler_en"], collection["classification"], collection["authenticity_en"],
                collection["edition_en"], collection["edition_ar"],
            ),
        )
        hadith_batch = []
        reference_batch = []
        seen_numbers: set[str] = set()
        for row in english.get("hadiths", []):
            if not isinstance(row, dict):
                continue
            hadith_number = text(row.get("hadithnumber"))
            if not hadith_number or hadith_number in seen_numbers:
                continue
            seen_numbers.add(hadith_number)
            english_arabic_number = text(row.get("arabicnumber"))
            arabic_row = arabic_by_hadith.get(hadith_number) or arabic_by_number.get(english_arabic_number) or {}
            reference = row.get("reference") if isinstance(row.get("reference"), dict) else {}
            arabic_reference = arabic_row.get("reference") if isinstance(arabic_row.get("reference"), dict) else {}
            book_number = text(reference.get("book") or arabic_reference.get("book"))
            in_book_hadith = text(reference.get("hadith") or arabic_reference.get("hadith"))
            section_number = book_number
            section_en = english_sections.get(section_number, "")
            section_ar_raw = arabic_sections.get(section_number, "")
            section_ar = section_ar_raw if has_arabic(section_ar_raw) else ""
            grades = grade_rows(row.get("grades"), arabic_row.get("grades"))
            if grades:
                graded += 1
            arabic_number = text(arabic_row.get("arabicnumber") or row.get("arabicnumber"))
            translation = text(row.get("text"))
            arabic_text = text(arabic_row.get("text"))
            if not translation and not arabic_text:
                continue
            source_url = exact_source_url(collection["edition_en"], hadith_number)
            hadith_batch.append((
                collection["slug"], hadith_number, section_en, arabic_text, translation,
                json.dumps(grades, ensure_ascii=False, separators=(",", ":")), source_url,
            ))
            reference_batch.append((
                collection["slug"], hadith_number, arabic_number, section_number, section_en, section_ar,
                book_number, in_book_hadith, collection["edition_en"], collection["edition_ar"],
                PROVIDER_NAME, PROVIDER_REPOSITORY,
            ))
        connection.executemany(
            "insert into hadiths(collection_slug,hadith_number,section_en,arabic_text,translation_en,grades_json,source_url) values(?,?,?,?,?,?,?)",
            hadith_batch,
        )
        connection.executemany(
            "insert into hadith_references(collection_slug,hadith_number,arabic_number,section_number,section_en,section_ar,book_number,in_book_hadith,source_edition_en,source_edition_ar,provider_name,provider_url) values(?,?,?,?,?,?,?,?,?,?,?,?)",
            reference_batch,
        )
        total += len(hadith_batch)
        connection.commit()
        print(f"Packaged {collection['slug']}: {len(hadith_batch)} records")

    metadata = {
        "schema_version": "2",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "provider_name": PROVIDER_NAME,
        "provider_repository": PROVIDER_REPOSITORY,
        "provider_version": PROVIDER_VERSION,
        "record_count": str(total),
        "graded_record_count": str(graded),
        "collection_count": str(len(COLLECTIONS)),
    }
    connection.executemany("insert into package_metadata(key,value) values(?,?)", metadata.items())
    connection.commit()
    connection.execute("vacuum")
    connection.close()
    print(f"Built {output} with {total} records; {graded} include named grading data")
    if total < 35000:
        raise RuntimeError(f"Hadith package is unexpectedly incomplete: {total}")
    return output


if __name__ == "__main__":
    build()
