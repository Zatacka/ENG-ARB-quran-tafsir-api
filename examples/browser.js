const API_URL = "https://your-api-domain.example";

export async function getTafsir(language, tafsir, surah, ayah) {
  const url = new URL(
    `/api/v1/languages/${language}/resources/${tafsir}/ayahs/${surah}/${ayah}`,
    API_URL,
  );
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Tafsir API request failed: ${response.status}`);
  }
  return response.json();
}

export async function compareEnglishAndArabicIbnKathir(surah, ayah) {
  const url = new URL(`/api/v1/ayahs/${surah}/${ayah}/compare`, API_URL);
  url.searchParams.append("selection", "en:tafsir-ibn-kathir");
  url.searchParams.append("selection", "ar:tafsir-ibn-kathir");
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Tafsir comparison failed: ${response.status}`);
  }
  return response.json();
}
