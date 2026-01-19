import json
import os
import time
import sys

# 강제로 UTF-8 출력 설정 (윈도우 출력 오류 방지)
sys.stdout.reconfigure(encoding='utf-8')

try:
    from googletrans import Translator
except ImportError:
    print("[Error] googletrans 라이브러리가 없습니다.")
    print("pip install googletrans==4.0.0-rc1 명령어를 실행해주세요.")
    sys.exit(1)

# 파일 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(BASE_DIR, "augments_global_en.json")
OUTPUT_FILE = os.path.join(BASE_DIR, "augments_global_ko.json")

def translate_tips():
    print("[Start] 스크립트 실행 시작...")
    
    if not os.path.exists(INPUT_FILE):
        print(f"[Error] 파일을 찾을 수 없습니다: {INPUT_FILE}")
        return

    print(f"[Info] 데이터 파일 로딩 중... ({INPUT_FILE})")
    
    try:
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[Error] JSON 파일 읽기 실패: {e}")
        return

    translator = Translator()
    total = len(data)
    print(f"[Info] 총 {total}개의 증강 데이터 번역을 시도합니다.")

    translated_data = []
    
    for idx, item in enumerate(data):
        new_item = item.copy()
        
        # 팁 가져오기
        tips = item.get("tips") or item.get("tips_flat") or item.get("notes") or []
        if isinstance(tips, str):
            tips = [tips]
            
        korean_tips = []
        if tips:
            for t in tips:
                if not t or not isinstance(t, str): continue
                try:
                    # 너무 짧거나 번역 불필요한 건 패스
                    if len(t) < 2:
                        korean_tips.append(t)
                        continue
                        
                    res = translator.translate(t, src='en', dest='ko')
                    korean_tips.append(res.text)
                except Exception as e:
                    # 번역 실패 시 원본 유지하고 계속 진행
                    # print(f"[Warn] 번역 실패: {e}") 
                    korean_tips.append(t)
                # 차단 방지 딜레이
                time.sleep(0.1)
        
        new_item["tips"] = korean_tips
        translated_data.append(new_item)
        
        # 진행 상황 표시 (10개마다)
        if (idx + 1) % 10 == 0:
            print(f"[Progress] {idx+1}/{total} 완료...")

    # 파일 저장
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(translated_data, f, ensure_ascii=False, indent=2)
        print(f"[Success] 번역 완료! 파일 생성됨: {OUTPUT_FILE}")
    except Exception as e:
        print(f"[Error] 파일 저장 실패: {e}")

if __name__ == "__main__":
    translate_tips()