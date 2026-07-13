from __future__ import annotations

import argparse
import hashlib
import shutil
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DATASET_DIR = PROJECT_ROOT / "dataset"
ARCHIVE_NAME = "tafsir-data.zip"


def build(part_size_mib: int = 20) -> None:
    if not DATA_DIR.is_dir():
        raise RuntimeError(f"Missing data directory: {DATA_DIR}")
    DATASET_DIR.mkdir(exist_ok=True)
    for old in DATASET_DIR.glob("tafsir-data.zip.part*"):
        old.unlink()
    archive_path = DATASET_DIR / ARCHIVE_NAME
    if archive_path.exists():
        archive_path.unlink()

    with zipfile.ZipFile(
        archive_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=1,
        allowZip64=True,
    ) as archive:
        for path in sorted(DATA_DIR.rglob("*.db")):
            archive.write(path, path.relative_to(PROJECT_ROOT).as_posix())

    digest_object = hashlib.sha256()
    with archive_path.open('rb') as source:
        while chunk := source.read(1024 * 1024):
            digest_object.update(chunk)
    digest = digest_object.hexdigest()
    (DATASET_DIR / "tafsir-data.sha256").write_text(
        f"{digest}  {ARCHIVE_NAME}\n", encoding="utf-8"
    )

    part_size = part_size_mib * 1024 * 1024
    with archive_path.open("rb") as source:
        number = 1
        while chunk := source.read(part_size):
            part = DATASET_DIR / f"{ARCHIVE_NAME}.part{number:03d}"
            part.write_bytes(chunk)
            number += 1
    archive_path.unlink()
    print(f"Created {number - 1} parts of at most {part_size_mib} MiB")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build split dataset archive")
    parser.add_argument("--part-size-mib", type=int, default=20)
    args = parser.parse_args()
    build(args.part_size_mib)
