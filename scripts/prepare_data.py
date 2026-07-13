from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_FILE = PROJECT_ROOT / "catalog" / "resources.json"
DATASET_DIR = PROJECT_ROOT / "dataset"
DATA_DIR = PROJECT_ROOT / "data"
MARKER_FILE = DATA_DIR / ".dataset-sha256"
CHECKSUM_FILE = DATASET_DIR / "tafsir-data.sha256"


def expected_files() -> list[Path]:
    payload = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    return [DATA_DIR / item["database_file"] for item in payload["resources"]]


def expected_checksum() -> str:
    line = CHECKSUM_FILE.read_text(encoding="utf-8").strip()
    return line.split()[0]


def data_is_ready(checksum: str) -> bool:
    return (
        MARKER_FILE.is_file()
        and MARKER_FILE.read_text(encoding="utf-8").strip() == checksum
        and all(path.is_file() for path in expected_files())
    )


def safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.infolist():
        target = (destination / member.filename).resolve()
        if target != root and root not in target.parents:
            raise RuntimeError(f"Unsafe archive member: {member.filename}")
    archive.extractall(destination)


def prepare(force: bool = False) -> None:
    checksum = expected_checksum()
    if not force and data_is_ready(checksum):
        print(f"Dataset is already prepared in {DATA_DIR}")
        return

    parts = sorted(DATASET_DIR.glob("tafsir-data.zip.part*"))
    if not parts:
        raise RuntimeError(f"No dataset parts found in {DATASET_DIR}")

    with tempfile.TemporaryDirectory(prefix="quran-tafsir-data-") as temp_name:
        temp_dir = Path(temp_name)
        joined = temp_dir / "tafsir-data.zip"
        digest = hashlib.sha256()
        with joined.open("wb") as output:
            for part in parts:
                print(f"Reading {part.name}")
                with part.open("rb") as source:
                    while chunk := source.read(1024 * 1024):
                        digest.update(chunk)
                        output.write(chunk)
        actual = digest.hexdigest()
        if actual != checksum:
            raise RuntimeError(
                f"Dataset checksum mismatch: expected {checksum}, received {actual}"
            )

        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir()
        with zipfile.ZipFile(joined) as archive:
            safe_extract(archive, extract_dir)

        extracted_data = extract_dir / "data"
        if not extracted_data.is_dir():
            raise RuntimeError("Dataset archive does not contain a data directory")
        if DATA_DIR.exists():
            shutil.rmtree(DATA_DIR)
        shutil.move(str(extracted_data), str(DATA_DIR))
        MARKER_FILE.write_text(checksum + "\n", encoding="utf-8")

    missing = [str(path) for path in expected_files() if not path.is_file()]
    if missing:
        raise RuntimeError(f"Dataset extraction is incomplete: {missing[:3]}")
    print(f"Prepared {len(expected_files())} databases in {DATA_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reconstruct and extract tafsir data")
    parser.add_argument("--force", action="store_true", help="replace existing extracted data")
    args = parser.parse_args()
    prepare(force=args.force)
