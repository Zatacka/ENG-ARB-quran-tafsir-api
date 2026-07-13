from __future__ import annotations

import json
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path

API_VERSION = "1"
BASE = f"https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@{API_VERSION}/editions"
OUT = Path("out/wic-hadith-core.sqlite3")

COLLECTIONS = [
    {"slug":"bukhari","name_en":"Sahih al-Bukhari","name_ar":"صحيح البخاري","compiler_en":"Imam Muhammad al-Bukhari","classification":"sahih","authenticity_en":"A primary canonical collection whose compiler intended to include authentic reports under his conditions.","edition_en":"eng-bukhari","edition_ar":"ara-bukhari"},
    {"slug":"muslim","name_en":"Sahih Muslim","name_ar":"صحيح مسلم","compiler_en":"Imam Muslim ibn al-Hajjaj","classification":"sahih","authenticity_en":"A primary canonical collection whose compiler intended to include authentic reports under his conditions.","edition_en":"eng-muslim","edition_ar":"ara-muslim"},
    {"slug":"abudawud","name_en":"Sunan Abi Dawud","name_ar":"سنن أبي داود","compiler_en":"Imam Abu Dawud al-Sijistani","classification":"sunan","authenticity_en":"A major Sunan collection containing reports of differing grades. Use the displayed grading and specialist scholarship.","edition_en":"eng-abudawud","edition_ar":"ara-abudawud"},
    {"slug":"tirmidhi","name_en":"Jami at-Tirmidhi","name_ar":"جامع الترمذي","compiler_en":"Imam Muhammad at-Tirmidhi","classification":"sunan","authenticity_en":"A major collection that frequently records scholarly grading and legal discussion; reports have differing grades.","edition_en":"eng-tirmidhi","edition_ar":"ara-tirmidhi"},
    {"slug":"nasai","name_en":"Sunan an-Nasa'i","name_ar":"سنن النسائي","compiler_en":"Imam Ahmad an-Nasa'i","classification":"sunan","authenticity_en":"A major Sunan collection containing reports of differing grades. Use the displayed grading and specialist scholarship.","edition_en":"eng-nasai","edition_ar":"ara-nasai"},
    {"slug":"ibnmajah","name_en":"Sunan Ibn Majah","name_ar":"سنن ابن ماجه","compiler_en":"Imam Ibn Majah al-Qazwini","classification":"sunan","authenticity_en":"A major Sunan collection containing reports of differing grades. Use the displayed grading and specialist scholarship.","edition_en":"eng-ibnmajah","edition_ar":"ara-ibnmajah"},
    {"slug":"malik","name_en":"Muwatta Malik","name_ar":"موطأ مالك","compiler_en":"Imam Malik ibn Anas","classification":"muwatta","authenticity_en":"An early hadith and legal collection containing marfu, mawquf and other reports with scholarly transmission context.","edition_en":"eng-malik","edition_ar":"ara-malik"},
    {"slug":"nawawi","name_en":"Forty Hadith of an-Nawawi","name_ar":"الأربعون النووية","compiler_en":"Imam Yahya an-Nawawi","classification":"curated","authenticity_en":"A foundational curated collection of comprehensive hadiths selected by Imam an-Nawawi.","edition_en":"eng-nawawi","edition_ar":"ara-nawawi"},
    {"slug":"qudsi","name_en":"Forty Hadith Qudsi","name_ar":"الأربعون القدسية","compiler_en":"Curated collection","classification":"curated","authenticity_en":"A thematic curated collection. Individual source references and grades should be consulted.","edition_en":"eng-qudsi","edition_ar":"ara-qudsi"},
    {"slug":"dehlawi","name_en":"Forty Hadith Shah Waliullah Dehlawi","name_ar":"الأربعون للدهلوي","compiler_en":"Shah Waliullah Dehlawi","classification":"curated","authenticity_en":"A curated forty-hadith collection. Individual source references and grades should be consulted.","edition_en":"eng-dehlawi","edition_ar":"ara-dehlawi"}
]

def fetch_json(edition: str) -> dict:
    urls=[f"{BASE}/{edition}.min.json",f"{BASE}/{edition}.json"]
    last=None
    for attempt in range(4):
        for url in urls:
            try:
                req=urllib.request.Request(url,headers={"User-Agent":"WIC-Hadith-Package/1.0"})
                with urllib.request.urlopen(req,timeout=120) as response:
                    return json.loads(response.read().decode("utf-8"))
            except (urllib.error.URLError,TimeoutError,json.JSONDecodeError) as exc:
                last=exc
        time.sleep(2**attempt)
    raise RuntimeError(f"Could not download {edition}: {last}")

def number_key(value: object) -> str:
    if isinstance(value,float) and value.is_integer(): return str(int(value))
    return str(value if value is not None else "").strip()

def section_intervals(payload: dict) -> list[tuple[float,float,str]]:
    metadata=payload.get("metadata") or {}; names=metadata.get("section") or {}; details=metadata.get("section_detail") or {}; result=[]
    for key,detail in details.items():
        if not isinstance(detail,dict): continue
        try: start=float(detail.get("hadithnumber_first")); end=float(detail.get("hadithnumber_last"))
        except (TypeError,ValueError): continue
        result.append((start,end,str(names.get(str(key),names.get(key,"")) or "")))
    return result

def chapter_for(number: str, intervals: list[tuple[float,float,str]]) -> str:
    try: numeric=float(number)
    except ValueError: return ""
    return next((title for start,end,title in intervals if start<=numeric<=end),"")

def rows_by_number(payload: dict) -> dict[str,dict]:
    result={}
    for item in payload.get("hadiths") or []:
        if not isinstance(item,dict): continue
        key=number_key(item.get("hadithnumber"))
        if key and key not in result: result[key]=item
    return result

def create_schema(db: sqlite3.Connection) -> None:
    db.executescript("""
    PRAGMA journal_mode=DELETE;
    PRAGMA synchronous=FULL;
    CREATE TABLE package_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE collections(slug TEXT PRIMARY KEY,name_en TEXT NOT NULL,name_ar TEXT NOT NULL DEFAULT '',compiler_en TEXT NOT NULL DEFAULT '',classification TEXT NOT NULL DEFAULT '',authenticity_en TEXT NOT NULL DEFAULT '',cover_path TEXT NOT NULL DEFAULT '');
    CREATE TABLE hadiths(id INTEGER PRIMARY KEY AUTOINCREMENT,collection_slug TEXT NOT NULL,hadith_number TEXT NOT NULL,section_en TEXT NOT NULL DEFAULT '',arabic_text TEXT NOT NULL DEFAULT '',translation_en TEXT NOT NULL DEFAULT '',grades_json TEXT NOT NULL DEFAULT '[]',source_url TEXT NOT NULL DEFAULT '',UNIQUE(collection_slug,hadith_number),FOREIGN KEY(collection_slug) REFERENCES collections(slug) ON DELETE CASCADE);
    CREATE INDEX ix_hadiths_collection_number ON hadiths(collection_slug,hadith_number);
    """)

def sortable(value: str):
    try: return (0,float(value),value)
    except ValueError: return (1,0,value)

def main() -> None:
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.unlink(missing_ok=True)
    db=sqlite3.connect(OUT)
    try:
        db.execute("PRAGMA foreign_keys=ON"); create_schema(db)
        db.executemany("INSERT INTO package_meta(key,value) VALUES (?,?)",[("format","wic-hadith-package-v1"),("provider","Hadith API by Fawaz Ahmed"),("provider_repository","https://github.com/fawazahmed0/hadith-api"),("api_version",API_VERSION),("language_pair","Arabic and English")])
        total=0
        for collection in COLLECTIONS:
            print(f"Downloading {collection['name_en']}...")
            english=fetch_json(collection["edition_en"]); arabic=fetch_json(collection["edition_ar"])
            english_rows=rows_by_number(english); arabic_rows=rows_by_number(arabic); intervals=section_intervals(english)
            db.execute("INSERT INTO collections(slug,name_en,name_ar,compiler_en,classification,authenticity_en,cover_path) VALUES (?,?,?,?,?,?,?)",(collection["slug"],collection["name_en"],collection["name_ar"],collection["compiler_en"],collection["classification"],collection["authenticity_en"],""))
            batch=[]
            for key in sorted(set(english_rows)|set(arabic_rows),key=sortable):
                en=english_rows.get(key,{}); ar=arabic_rows.get(key,{})
                translation=str(en.get("text") or "").strip(); arabic_text=str(ar.get("text") or "").strip()
                if not translation and not arabic_text: continue
                grades=en.get("grades") if isinstance(en.get("grades"),list) else []
                batch.append((collection["slug"],key,chapter_for(key,intervals),arabic_text,translation,json.dumps(grades,ensure_ascii=False,separators=(",",":")),f"https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@{API_VERSION}/editions/{collection['edition_en']}/{key}.json"))
            db.executemany("INSERT INTO hadiths(collection_slug,hadith_number,section_en,arabic_text,translation_en,grades_json,source_url) VALUES (?,?,?,?,?,?,?)",batch)
            total+=len(batch); db.commit(); print(f"  {len(batch):,} records")
        db.execute("INSERT INTO package_meta(key,value) VALUES (?,?)",("record_count",str(total))); db.execute("ANALYZE")
        result=db.execute("PRAGMA integrity_check").fetchone()[0]
        if result!="ok": raise RuntimeError(f"SQLite integrity check failed: {result}")
        db.commit(); print(f"Created {OUT} with {total:,} records")
    finally: db.close()

if __name__=="__main__": main()
