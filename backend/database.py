import os
import sys
import json
import sqlite3
import difflib

# ==========================================
# 1. 유틸리티 & 설정
# ==========================================

# PyInstaller 경로 대응
def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# 파일 경로 설정
GLOBAL_AUG_JSON_PATH = resource_path("augments_global_ko.json")
MAPPING_TXT_PATH = resource_path("augment_mapping_full.txt")
DB_NAME = resource_path("game_data.db")

# 🔥 [핵심] 문자열 정규화 함수 (Regex 사용)
# 모든 특수문자와 공백을 제거하고 소문자만 남김
# "Kog'Maw" -> "kogmaw", "전환: 프리즘" -> "전환프리즘"
import re
def normalize_name(name):
    if not name: return ""

    EXCEPTION_MAP = {
        "MonkeyKing": "wukong",
    }

    if name in EXCEPTION_MAP:
        return EXCEPTION_MAP[name]

    # 한글, 영어, 숫자만 남기고 나머지(공백, 특수문자) 다 제거
    return re.sub(r'[^a-zA-Z0-9가-힣]', '', name).lower()

# ==========================================
# 2. 전역 변수 (캐싱용)
# ==========================================
# 챔피언 데이터 캐시
_CHAMPION_CACHE_NORMALIZED = {} # {"kaisa": {tier: S, ...}}

# 증강 데이터 캐시
_AUGMENT_MAP_KO_TO_EN = {}      # 원본 한글 -> 영어
_AUGMENT_MAP_NORMALIZED = {}    # 정규화된 한글 -> 영어 (검색용)
_GLOBAL_AUG_STATS = {}          # 정규화된 영어 -> 증강 통계 데이터

# 데이터 로드 여부 플래그
_IS_DATA_LOADED = False

def get_connection():
    return sqlite3.connect(DB_NAME)

# ==========================================
# 3. 초기화 및 데이터 로드
# ==========================================

def init_db():
    """데이터베이스 테이블 생성 및 초기 데이터 로드"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 테이블 생성
    cursor.execute('''CREATE TABLE IF NOT EXISTS champions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, role TEXT, tier TEXT,
        win_rate TEXT, pick_rate TEXT, ban_rate TEXT, score TEXT, detail_url TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS augments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, champion_name TEXT, augment_type TEXT,
        augment_name TEXT, augment_tier TEXT,
        FOREIGN KEY(champion_name) REFERENCES champions(name))''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS augment_name_map (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name_ko TEXT NOT NULL UNIQUE, name_en TEXT NOT NULL)''')
    
    conn.commit()
    conn.close()
    
    # 텍스트 파일 내용을 DB에 넣기 (최초 1회)
    _import_mapping_txt_to_db()
    
    # 메모리에 데이터 로드 (고속 검색을 위해)
    load_all_data_to_memory()

def _import_mapping_txt_to_db():
    """augment_mapping_full.txt 파일 내용을 DB로 이관"""
    if not os.path.exists(MAPPING_TXT_PATH): return
    
    conn = get_connection()
    cur = conn.cursor()
    try:
        with open(MAPPING_TXT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line: # 포맷이 "한글=영어" 인 경우
                    ko, en = line.strip().split("=", 1)
                    cur.execute("INSERT OR IGNORE INTO augment_name_map(name_ko, name_en) VALUES(?, ?)", (ko, en))
                elif " : " in line: # 포맷이 "한글 : 영어" 인 경우 (구버전 호환)
                    ko, en = line.strip().split(" : ", 1)
                    cur.execute("INSERT OR IGNORE INTO augment_name_map(name_ko, name_en) VALUES(?, ?)", (ko, en))
        conn.commit()
    except Exception as e:
        print(f"[DB] 매핑 파일 임포트 중 오류: {e}")
    finally:
        conn.close()

def load_all_data_to_memory():
    """DB와 JSON 데이터를 읽어 정규화된 맵(Dictionary)을 생성"""
    global _CHAMPION_CACHE_NORMALIZED
    global _AUGMENT_MAP_KO_TO_EN, _AUGMENT_MAP_NORMALIZED
    global _GLOBAL_AUG_STATS, _IS_DATA_LOADED

    if _IS_DATA_LOADED: return

    # 1. 챔피언 정보 로드
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name, tier, win_rate, score FROM champions")
    rows = cur.fetchall()
    
    _CHAMPION_CACHE_NORMALIZED = {}
    for r in rows:
        # 키를 정규화해서 저장 (예: "Kog'Maw" -> "kogmaw")
        clean_name = normalize_name(r[0])
        _CHAMPION_CACHE_NORMALIZED[clean_name] = {
            'name': r[0], 'tier': r[1], 'win_rate': r[2], 'score': r[3]
        }

    # 2. 증강 이름 매핑 로드 (DB -> Memory)
    cur.execute("SELECT name_ko, name_en FROM augment_name_map")
    map_rows = cur.fetchall()
    conn.close()

    _AUGMENT_MAP_KO_TO_EN = {}
    _AUGMENT_MAP_NORMALIZED = {}
    
    for ko, en in map_rows:
        _AUGMENT_MAP_KO_TO_EN[ko] = en
        
        # 🔥 한글 이름 정규화해서 저장 (예: "지옥의 계약" -> "지옥의계약")
        clean_ko = normalize_name(ko)
        _AUGMENT_MAP_NORMALIZED[clean_ko] = en

    # 3. 범용 증강 통계 로드 (JSON -> Memory)
    _GLOBAL_AUG_STATS = {}
    if os.path.exists(GLOBAL_AUG_JSON_PATH):
        try:
            with open(GLOBAL_AUG_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            items = data if isinstance(data, list) else data.values()
            
            for item in items:
                name_en = item.get("name_en", "").strip()
                if name_en:
                    # 🔥 영어 이름 정규화해서 저장 (예: "Infernal Contract" -> "infernalcontract")
                    clean_en = normalize_name(name_en)
                    _GLOBAL_AUG_STATS[clean_en] = item
        except Exception as e:
            print(f"[DB] 범용 JSON 로드 실패: {e}")

    _IS_DATA_LOADED = True
    print(f"[DB] 메모리 로드 완료: 챔피언({len(_CHAMPION_CACHE_NORMALIZED)}), 증강매핑({len(_AUGMENT_MAP_NORMALIZED)})")

# ==========================================
# 4. 데이터 조회 함수 (외부 호출용)
# ==========================================

def get_champion_info(name):
    """챔피언 정보 조회 (정규화 적용)"""
    if not _IS_DATA_LOADED: load_all_data_to_memory()
    
    # 입력된 이름 정규화 후 검색 (Kog'Maw, LeBlanc 등 해결)
    clean_name = normalize_name(name)
    return _CHAMPION_CACHE_NORMALIZED.get(clean_name)

def get_champion_augments(name):
    """
    챔피언 전용 증강 목록 조회
    DB에 'LeBlanc'으로 저장되어 있든, 'Kog'Maw'로 저장되어 있든 무조건 찾아냅니다.
    """
    if not _IS_DATA_LOADED: load_all_data_to_memory()
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # 🔥 [수정 핵심] SQL 내부에서 특수문자를 다 지우고 비교하는 쿼리
    # REPLACE 함수를 중첩해서 공백(' '), 따옴표('''), 점('.'), 앤드('&')를 다 지웁니다.
    # 주의: SQL에서 따옴표를 표현하려면 '' (두 개)를 써야 합니다.
    sql = """
        SELECT augment_type, augment_name, augment_tier 
        FROM augments 
        WHERE 
            REPLACE(
                REPLACE(
                    REPLACE(
                        REPLACE(LOWER(champion_name), ' ', ''), 
                    '''', ''), 
                '.', ''), 
            '&', '') = ?
    """
    
    # 파이썬에서도 똑같이 정규화해서 넣어줍니다.
    clean_name = normalize_name(name)
    
    cursor.execute(sql, (clean_name,))
    rows = cursor.fetchall()
    conn.close()
    
    # 결과 반환
    return [{'type': r[0], 'name': r[1], 'tier': r[2]} for r in rows]

def enrich_ocr_augments(names_ko):
    """
    OCR로 읽은 한글 증강 이름 리스트를 받아서,
    영어 이름 매핑 및 티어 정보를 포함하여 반환
    """
    if not _IS_DATA_LOADED: load_all_data_to_memory()
    
    results = []
    seen_names = set() # 중복 제거용

    for raw_ko in names_ko:
        if not raw_ko: continue
        
        # 1. OCR 결과 정규화
        clean_ko = normalize_name(raw_ko)
        if clean_ko in seen_names: continue
        seen_names.add(clean_ko)

        # 2. 한글 -> 영어 이름 찾기
        # (A) 원본 매핑 시도
        name_en = _AUGMENT_MAP_KO_TO_EN.get(raw_ko)
        # (B) 실패 시 정규화 매핑 시도 (핵심!)
        if not name_en:
            name_en = _AUGMENT_MAP_NORMALIZED.get(clean_ko)
            
        # (C) 그래도 없으면 Difflib(유사도) 검사 (최후의 수단)
        if not name_en:
            # 모든 한글 키를 대상으로 유사도 검사
            all_ko_keys = list(_AUGMENT_MAP_NORMALIZED.keys())
            matches = difflib.get_close_matches(clean_ko, all_ko_keys, n=1, cutoff=0.6)
            if matches:
                name_en = _AUGMENT_MAP_NORMALIZED[matches[0]]

        # 영어 이름을 못 찾았어도 한글 이름이라도 보여주기 위해 유지
        if not name_en:
            # print(f"[DB] Unknown Augment: {raw_ko} (Norm: {clean_ko})")
            name_en = "" # 빈 문자열로 유지
            
        # 3. 글로벌 통계 데이터 조회
        # ... (이하 로직은 name_en이 있으면 찾고, 없으면 기본값 사용)
        
        # 영어 정규화 키
        clean_en = normalize_name(name_en) if name_en else ""
        stats = _GLOBAL_AUG_STATS.get(clean_en, {})

        # 3. 영어 이름 -> 범용 통계 찾기
        clean_en = normalize_name(name_en)
        stats = _GLOBAL_AUG_STATS.get(clean_en)

        # 결과 생성
        item = {
            "name_ko": raw_ko, # 화면에 보여줄 원본 이름
            "name_en": name_en,
            "tier_global": stats.get("tier_global") or stats.get("tier") or "?",
            "win_rate": stats.get("win_rate", "-"),
            "pick_rate": stats.get("pick_rate", "-"),
            "tips": stats.get("tips", [])[:2] if stats else []
        }
        results.append(item)
        
    return results

# 파일 실행 시 초기화
init_db()