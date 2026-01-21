import sqlite3
import os

# 파일 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "game_data.db")
MAPPING_TXT_PATH = os.path.join(BASE_DIR, "augment_mapping_full.txt")

def update_db_mapping():
    # 1. 파일 존재 여부 확인
    if not os.path.exists(DB_PATH):
        print(f"❌ DB 파일을 찾을 수 없습니다: {DB_PATH}")
        print("서버(app.py)를 한 번이라도 실행해야 DB가 생성됩니다.")
        return
    
    if not os.path.exists(MAPPING_TXT_PATH):
        print(f"❌ 매핑 텍스트 파일을 찾을 수 없습니다: {MAPPING_TXT_PATH}")
        return

    # 2. DB 연결
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # 테이블이 없을 경우를 대비해 생성 (안전장치)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS augment_name_map (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name_ko TEXT NOT NULL UNIQUE,
            name_en TEXT NOT NULL
        )
    """)
    
    print("🔄 매핑 테이블 업데이트 시작...")
    
    count = 0
    updated_count = 0
    
    # 3. 텍스트 파일 읽기 및 DB 갱신
    try:
        with open(MAPPING_TXT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if " : " in line:
                    # 텍스트 파일 파싱 ("한글명 : 영문명")
                    ko, en = line.strip().split(" : ", 1)
                    ko = ko.strip()
                    en = en.strip()
                    
                    if not ko or not en:
                        continue
                    
                    # ★ 핵심: INSERT OR REPLACE
                    # 기존에 해당 한글 이름이 있으면 영문명을 새것으로 덮어씁니다.
                    cur.execute("""
                        INSERT OR REPLACE INTO augment_name_map (name_ko, name_en) 
                        VALUES (?, ?)
                    """, (ko, en))
                    count += 1
        
        conn.commit()
        print(f"✅ 업데이트 완료! 총 {count}개의 항목을 처리했습니다.")
        print("이제 'app.py'를 다시 실행하면 새로운 매핑이 적용됩니다.")
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    update_db_mapping()