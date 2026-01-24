"""
OCR PoC: EasyOCR을 사용한 증강체 이름 인식 테스트
- Tesseract 대비 정확도 향상
- CPU 전용 모드로 실행
"""
import re
import cv2
import numpy as np
import time
import sys

try:
    import easyocr
except ImportError:
    print("❌ 'easyocr' 라이브러리가 설치되지 않았습니다.")
    print("pip install easyocr 명령어로 설치해주세요.")
    sys.exit(1)

# ==========================================
# 1. EasyOCR Reader 초기화 (전역, 한 번만 실행)
# ==========================================
print("[OCR] Loading EasyOCR Model (CPU Mode)... 잠시만 기다려주세요.")
reader = easyocr.Reader(['ko', 'en'], gpu=False)
print("[OCR] ✅ Model Loaded!")

# ==========================================
# 2. 핵심 함수
# ==========================================
def normalize_text(text):
    """특수문자 제거. 예: "전환: 프리즘!" -> "전환프리즘" """
    return re.sub(r'[^a-zA-Z0-9가-힣]', '', text).lower()

def extract_text_easyocr(image_bgr):
    """
    기존 Tesseract의 extract_title_text를 대체하는 함수
    Input: OpenCV BGR 이미지 (ROI 크롭된 이미지)
    Output: 정규화된 텍스트
    """
    try:
        # detail=0: 좌표 없이 텍스트 리스트만 반환
        results = reader.readtext(image_bgr, detail=0)
        
        if not results:
            return ""
        
        full_text = " ".join(results)
        return normalize_text(full_text)
        
    except Exception as e:
        print(f"[OCR] Error: {e}")
        return ""

# ==========================================
# 3. 테스트 실행
# ==========================================
if __name__ == "__main__":
    print("\n--- EasyOCR PoC Test ---")
    
    # 더미 이미지 (검은 배경 + 흰 글씨)
    dummy_img = np.zeros((80, 500, 3), dtype=np.uint8)
    cv2.putText(dummy_img, "Test: Prismatic", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)
    
    start = time.time()
    result = extract_text_easyocr(dummy_img)
    elapsed = time.time() - start
    
    print(f"Result: '{result}'")
    print(f"Time  : {elapsed:.3f} sec")
    print("\n✅ EasyOCR PoC 완료!")
    print("⚠️ CPU 환경에서는 Tesseract보다 느릴 수 있으나, 정확도가 높습니다.")
