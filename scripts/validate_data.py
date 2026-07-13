from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_FILE = PROJECT_ROOT / "catalog" / "resources.json"
DATA_DIR = PROJECT_ROOT / "data"
REQUIRED_COLUMNS = {
    "ayah_key", "group_ayah_key", "from_ayah", "to_ayah", "ayah_keys", "text"
}
KEY_PATTERN = re.compile(r"^\d{1,3}:\d{1,3}$")
EXPECTED_AYAHS = 6236


def validate() -> int:
    catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    errors: list[str] = []
    canonical_keys: set[str] | None = None

    print(f"Validating {len(catalog['resources'])} databases")
    print("-")
    for item in catalog["resources"]:
        identifier = f"{item['language_code']}:{item['slug']}"
        path = DATA_DIR / item["database_file"]
        if not path.is_file():
            errors.append(f"{identifier}: missing {path}")
            continue
        connection = sqlite3.connect(str(path))
        connection.row_factory = sqlite3.Row
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            columns = {row[1] for row in connection.execute("PRAGMA table_info(tafsir)")}
            count = int(connection.execute("SELECT COUNT(*) FROM tafsir").fetchone()[0])
            distinct = int(
                connection.execute("SELECT COUNT(DISTINCT ayah_key) FROM tafsir").fetchone()[0]
            )
            keys = {
                row[0] for row in connection.execute("SELECT ayah_key FROM tafsir")
            }
            malformed = [key for key in keys if not KEY_PATTERN.fullmatch(key or "")]
            if integrity != "ok":
                errors.append(f"{identifier}: integrity_check={integrity}")
            if not REQUIRED_COLUMNS.issubset(columns):
                errors.append(
                    f"{identifier}: missing columns {sorted(REQUIRED_COLUMNS - columns)}"
                )
            if count != EXPECTED_AYAHS or distinct != EXPECTED_AYAHS:
                errors.append(
                    f"{identifier}: rows={count}, distinct_keys={distinct}, expected={EXPECTED_AYAHS}"
                )
            if malformed:
                errors.append(f"{identifier}: malformed keys {malformed[:5]}")
            if canonical_keys is None:
                canonical_keys = keys
            elif keys != canonical_keys:
                errors.append(f"{identifier}: ayah-key set differs from the canonical set")
            if int(item["ayah_count"]) != EXPECTED_AYAHS:
                errors.append(f"{identifier}: catalog ayah_count is incorrect")
            if int(item["available_ayahs"]) + int(item["missing_ayahs"]) != EXPECTED_AYAHS:
                errors.append(f"{identifier}: catalog coverage totals are inconsistent")
            print(
                f"{identifier:50} integrity={integrity:2} rows={count:4} "
                f"available={int(item['available_ayahs']):4} missing={int(item['missing_ayahs']):4}"
            )
        finally:
            connection.close()

    print("-")
    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("All databases passed validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(validate())
