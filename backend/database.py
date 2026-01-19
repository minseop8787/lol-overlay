import os
import sys
import json
import sqlite3
import difflib

# PyInstaller로 패키징했을 때 임시 폴더 경로를 찾는 함수
def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

GLOBAL_AUG_JSON_PATH = resource_path("augments_global_ko.json")
MAPPING_TXT_PATH = resource_path("augment_mapping_full.txt")
DB_NAME = resource_path("game_data.db")

_GLOBAL_AUG_BY_EN = None
_ALL_KO_NAMES = None

def get_connection():
    return sqlite3.connect(DB_NAME)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    # 챔피언 테이블
    cursor.execute('''CREATE TABLE IF NOT EXISTS champions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, role TEXT, tier TEXT,
        win_rate TEXT, pick_rate TEXT, ban_rate TEXT, score TEXT, detail_url TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    # 증강 테이블
    cursor.execute('''CREATE TABLE IF NOT EXISTS augments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, champion_name TEXT, augment_type TEXT,
        augment_name TEXT, augment_tier TEXT,
        FOREIGN KEY(champion_name) REFERENCES champions(name))''')
    # 매핑 테이블
    cursor.execute('''CREATE TABLE IF NOT EXISTS augment_name_map (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name_ko TEXT NOT NULL UNIQUE, name_en TEXT NOT NULL)''')
    conn.commit()
    conn.close()
    
    # 텍스트 파일에서 매핑 데이터 로드 (자동 수행)
    _import_mapping_txt()

def _import_mapping_txt():
    if not os.path.exists(MAPPING_TXT_PATH): return
    conn = get_connection()
    cur = conn.cursor()
    with open(MAPPING_TXT_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if " : " in line:
                ko, en = line.strip().split(" : ", 1)
                cur.execute("INSERT OR IGNORE INTO augment_name_map(name_ko, name_en) VALUES(?, ?)", (ko, en))
    conn.commit()
    conn.close()

def get_champion_info(name):
    conn = get_connection()
    cursor = conn.cursor()
    # 띄어쓰기 무시하고 검색 (TahmKench -> Tahm Kench 매칭 위함)
    cursor.execute("SELECT tier, win_rate, score FROM champions WHERE REPLACE(LOWER(name), ' ', '') = REPLACE(LOWER(?), ' ', '')", (name,))
    row = cursor.fetchone()
    conn.close()
    return {'tier': row[0], 'win_rate': row[1], 'score': row[2]} if row else None

def get_champion_augments(name):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT augment_type, augment_name, augment_tier FROM augments WHERE champion_name = ?", (name,))
    rows = cursor.fetchall()
    conn.close()
    return [{'type': r[0], 'name': r[1], 'tier': r[2]} for r in rows]

# --- Fuzzy Logic ---
def _load_ko_names():
    global _ALL_KO_NAMES
    if _ALL_KO_NAMES: return
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name_ko FROM augment_name_map")
    _ALL_KO_NAMES = [r[0] for r in cur.fetchall()]
    conn.close()

def resolve_augment_fuzzy(ocr_text):
    text = (ocr_text or "").strip()
    if not text: return None, None
    
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name_en FROM augment_name_map WHERE name_ko = ?", (text,))
    row = cur.fetchone()
    conn.close()
    
    if row: return text, row[0] # Exact Match

    _load_ko_names()
    matches = difflib.get_close_matches(text, _ALL_KO_NAMES, n=1, cutoff=0.5)
    if matches:
        corrected = matches[0]
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT name_en FROM augment_name_map WHERE name_ko = ?", (corrected,))
        row = cur.fetchone()
        conn.close()
        return corrected, row[0] if row else None
    
    return None, None

def _load_global_json():
    global _GLOBAL_AUG_BY_EN
    if _GLOBAL_AUG_BY_EN: return _GLOBAL_AUG_BY_EN
    if not os.path.exists(GLOBAL_AUG_JSON_PATH): return {}
    with open(GLOBAL_AUG_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    _GLOBAL_AUG_BY_EN = {item.get("name_en", "").strip(): item for item in data}
    return _GLOBAL_AUG_BY_EN

def enrich_ocr_augments(names_ko):
    out = []
    _load_global_json()
    for ko in names_ko:
        real_ko, en = resolve_augment_fuzzy(ko)
        meta = _GLOBAL_AUG_BY_EN.get(en) if en else None
        
        out.append({
            "name_ko": real_ko if real_ko else ko,
            "name_en": en,
            "tier_global": meta.get("tier_global") if meta else None,
            "tips": meta.get("tips", [])[:2] if meta else []
        })
    return out

init_db()