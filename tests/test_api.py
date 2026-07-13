from .conftest import client


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "language_count": 2,
        "resource_count": 60,
        "database_count": 60,
    }


def test_languages() -> None:
    response = client.get("/api/v1/languages")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert {item["code"] for item in payload["items"]} == {"en", "ar"}


def test_arabic_resources() -> None:
    response = client.get("/api/v1/languages/ar/resources")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 55
    assert any(item["slug"] == "tafsir-al-tabari" for item in payload["items"])
    assert any(item["resource_type"] == "dependency_graph" for item in payload["items"])


def test_english_grouped_commentary_is_resolved() -> None:
    response = client.get(
        "/api/v1/languages/en/resources/tazkirul-quran/ayahs/1/3"
    )
    assert response.status_code == 200
    item = response.json()["item"]
    assert item["requested_ayah_key"] == "1:3"
    assert item["source_ayah_key"] == "1:2"
    assert item["resolved_from_group"] is True
    assert item["available"] is True


def test_arabic_ayah() -> None:
    response = client.get(
        "/api/v1/languages/ar/resources/tafsir-al-tabari/ayahs/2/255"
    )
    assert response.status_code == 200
    item = response.json()["item"]
    assert item["available"] is True
    assert item["content_text"]
    assert item["resource"]["language_code"] == "ar"


def test_incomplete_source_is_explicit() -> None:
    response = client.get(
        "/api/v1/languages/ar/resources/tafsir-ibn-uthaymeen/ayahs/2/254"
    )
    assert response.status_code == 200
    item = response.json()["item"]
    assert item["available"] is False
    assert item["content_text"] is None
    assert item["missing_reason"] == "resource_has_no_content_for_ayah"


def test_multilingual_compare() -> None:
    response = client.get(
        "/api/v1/ayahs/2/255/compare",
        params=[
            ("selection", "en:tafsir-ibn-kathir"),
            ("selection", "ar:tafsir-ibn-kathir"),
        ],
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert payload["available_count"] == 2
    assert {item["resource"]["language_code"] for item in payload["items"]} == {"en", "ar"}


def test_arabic_search_normalizes_diacritics() -> None:
    response = client.get(
        "/api/v1/languages/ar/resources/tafsir-al-saddi/search",
        params={"q": "الرحمن", "limit": 3},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["normalized"] is True
    assert payload["pagination"]["total"] > 0


def test_svg_markup_can_be_requested() -> None:
    response = client.get(
        "/api/v1/languages/ar/resources/ayah-dependency-graphs/ayahs/1/1",
        params={"include_markup": "true"},
    )
    assert response.status_code == 200
    item = response.json()["item"]
    assert item["content_format"] == "svg"
    assert item["content_markup"].lstrip().startswith("<svg")


def test_legacy_english_route() -> None:
    response = client.get("/api/v1/tafsirs/tafsir-al-jalalayn/ayahs/1/1")
    assert response.status_code == 200
    assert response.json()["item"]["available"] is True


def test_invalid_ayah_returns_404() -> None:
    response = client.get(
        "/api/v1/languages/en/resources/tafsir-al-jalalayn/ayahs/1/99"
    )
    assert response.status_code == 404
