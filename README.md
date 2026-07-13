# Multilingual Quran Tafsir API

A read-only FastAPI service for English and Arabic Quran tafsir and related
Quranic-study resources. The repository provides one language-aware API rather
than maintaining separate English and Arabic services.

## Included data

- 2 languages: English and Arabic
- 60 databases in total
- 5 English tafsir resources
- 55 Arabic resources
- 6,236 canonical ayah rows per database
- Tafsir, i'rab, gharib al-Quran, qira'at, tadabbur, linguistic analysis, and
  ayah dependency graphs
- Automatic grouped-commentary resolution
- Explicit reporting when a source has no content for a requested ayah
- Diacritic-insensitive Arabic search
- English-Arabic comparison through one endpoint

See `RESOURCES.md` for the full catalog and `DATA_NOTICE.md` before making the
datasets public.

## Why the data is stored in split parts

The normalized databases expand to approximately 1.07 GiB. The repository
therefore stores one compressed dataset split into smaller files inside
`dataset/`. Do not manually combine them and do not upload the extracted
`data/` directory to GitHub.

During local setup, continuous integration, or a Docker build, this command
reconstructs the archive, verifies its SHA-256 checksum, and extracts all 60
databases:

```bash
python scripts/prepare_data.py
```

## Local setup

Python 3.13 or newer is recommended.

```bash
python -m venv .venv
```

Activate the virtual environment, then run:

```bash
python -m pip install --upgrade pip
pip install -e ".[dev]"
python scripts/prepare_data.py
python scripts/validate_data.py
pytest
uvicorn app.main:app --reload
```

Open:

- API documentation: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health`

## Core endpoints

List languages:

```http
GET /api/v1/languages
```

List every Arabic resource:

```http
GET /api/v1/languages/ar/resources
```

List Arabic tafsir only:

```http
GET /api/v1/languages/ar/tafsirs
```

Filter by resource type:

```http
GET /api/v1/languages/ar/resources?type=irab
GET /api/v1/languages/ar/resources?type=gharib
GET /api/v1/languages/ar/resources?type=qiraat
```

Retrieve English Tafsir Ibn Kathir for Ayat al-Kursi:

```http
GET /api/v1/languages/en/resources/tafsir-ibn-kathir/ayahs/2/255
```

Retrieve Arabic Tafsir Ibn Kathir:

```http
GET /api/v1/languages/ar/resources/tafsir-ibn-kathir/ayahs/2/255
```

Request the original HTML or SVG markup as well as plain text:

```http
GET /api/v1/languages/ar/resources/tafsir-al-tabari/ayahs/2/255?include_markup=true
```

Compare English and Arabic Ibn Kathir:

```http
GET /api/v1/ayahs/2/255/compare?selection=en:tafsir-ibn-kathir&selection=ar:tafsir-ibn-kathir
```

Compare multiple resources in one language:

```http
GET /api/v1/languages/ar/ayahs/2/255/compare?resource=tafsir-al-tabari&resource=tafsir-ibn-kathir&resource=tafsir-al-qurtubi
```

Search Arabic without requiring matching diacritics:

```http
GET /api/v1/languages/ar/resources/tafsir-al-saddi/search?q=الرحمن
```

Retrieve a surah with each ayah resolved to its grouped commentary source:

```http
GET /api/v1/languages/ar/resources/tafsir-al-tabari/surahs/1?mode=resolved
```

Retrieve only source commentary entries, without repeated grouped members:

```http
GET /api/v1/languages/ar/resources/tafsir-al-tabari/surahs/1?mode=compact
```

Retrieve a passage:

```http
GET /api/v1/languages/ar/resources/tafsir-al-tabari/passages/2/255/257
```

## Missing source coverage

Some supplied Arabic works do not contain commentary for every ayah. The API
returns the ayah record with:

```json
{
  "available": false,
  "content_text": null,
  "content_markup": null,
  "missing_reason": "resource_has_no_content_for_ayah"
}
```

This is different from an invalid ayah, which returns HTTP 404.

## Browser example

```javascript
const response = await fetch(
  "https://your-api-domain.example/api/v1/languages/ar/resources/tafsir-al-tabari/ayahs/2/255",
);

if (!response.ok) {
  throw new Error(`API request failed: ${response.status}`);
}

const { item } = await response.json();

if (item.available) {
  console.log(item.content_text);
}
```

A reusable example is included in `examples/browser.js`.

## Backward-compatible English routes

The original English-only routes remain available but are marked deprecated in
OpenAPI. For example:

```http
GET /api/v1/tafsirs/tafsir-ibn-kathir/ayahs/2/255
```

New integrations should use the language-aware routes.

## Configuration

Copy `.env.example` to `.env` for local configuration.

- `ALLOWED_ORIGINS`: comma-separated website origins allowed by CORS
- `API_KEY`: optional shared key expected in the `X-API-Key` header
- `CACHE_CONTROL`: response caching policy
- `TAFSIR_DATA_DIR`: optional custom extracted-data location

Do not place a private API key directly in public frontend JavaScript. A browser
website cannot securely hide a shared secret.

## Docker

```bash
docker compose up --build
```

The Docker build automatically reconstructs and validates the data. The split
archive is removed from the final image after extraction.

Because the extracted dataset is approximately 1.07 GiB, ensure that the chosen
hosting service allows a sufficiently large Docker image and build workspace.

## GitHub browser upload

Use the browser-upload package when uploading through GitHub's website. Extract
it first and upload everything inside the `quran-tafsir-api` folder. Keep every
file in `dataset/`; all parts are required.

The browser-upload package omits only `.github`. The API does not require that
folder. To add continuous integration later, create this file directly on
GitHub:

```text
.github/workflows/ci.yml
```

and copy the workflow from the complete package.

## Data integrity

The build process:

1. Reconstructs the split ZIP in numerical order.
2. Verifies its SHA-256 checksum.
3. Safely extracts the databases.
4. Confirms all catalog files exist.
5. Runs SQLite integrity and schema validation.

The two source databases that contained duplicated copies of all 6,236 ayah
rows were normalized to one row per ayah. No commentary text was rewritten.
