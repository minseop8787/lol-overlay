"""
augment_watcher.py - PaddleOCR(PP-OCRv5 Mobile) 버전
Tesseract를 제거하고 경량화된 딥러닝 모델을 사용합니다.
"""
import time
import threading
import re
import os
import difflib
import sys
from pathlib import Path

import numpy as np
import cv2
import mss
import requests

# =========================
# PaddleOCR 초기화
# =========================
try:
    from paddleocr import TextRecognition
    print("[Watcher] Loading PaddleOCR Model (korean_PP-OCRv5_mobile_rec)...")
    OCR_MODEL = TextRecognition(model_name="korean_PP-OCRv5_mobile_rec")
    print("[Watcher] ✅ PaddleOCR Model Loaded!")
    USE_PADDLE = True
except ImportError as e:
    print(f"[Watcher] ⚠️ PaddleOCR 로드 실패: {e}")
    print("[Watcher] Tesseract 폴백 모드로 전환합니다.")
    USE_PADDLE = False
    import pytesseract

# =========================
# PATH & SETTINGS
# =========================
def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

# Tesseract Fallback 경로
if not USE_PADDLE:
    portable_tesseract = resource_path(os.path.join("Tesseract-OCR", "tesseract.exe"))
    if os.path.exists(portable_tesseract):
        pytesseract.pytesseract.tesseract_cmd = portable_tesseract
    else:
        pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

MAPPING_TXT_PATH = Path(resource_path("augment_mapping_full.txt"))
POLL_INTERVAL = 0.2

# =========================
# 📐 해상도별 좌표 설정
# =========================
RESOLUTION_MAP = {
    1920: [
        (474, 412, 740, 447),
        (824, 412, 1093, 447),
        (1180, 412, 1447, 447)
    ],
    2560: [
        (789, 410, 1063, 448),
        (1143, 414, 1413, 446),
        (1500, 413, 1767, 447)
    ]
}

VALID_NAMES = []

def load_valid_names():
    global VALID_NAMES
    if not os.path.exists(MAPPING_TXT_PATH):
        return
    names = set()
    try:
        with open(MAPPING_TXT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if " : " in line:
                    ko, _ = line.split(" : ", 1)
                    names.add(ko.strip())
        VALID_NAMES = list(names)
        print(f"[Watcher] Loaded {len(VALID_NAMES)} valid augment names.")
    except Exception as e:
        print(f"[Watcher] Error loading mapping file: {e}")

def is_valid_text(text):
    if not VALID_NAMES: return True
    if text in VALID_NAMES: return True
    matches = difflib.get_close_matches(text, VALID_NAMES, n=1, cutoff=0.6)
    return len(matches) > 0

# =========================
# 이미지 처리 함수들
# =========================
def grab_screen_bgr(sct):
    try:
        monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        img = np.array(sct.grab(monitor))
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    except Exception as e:
        raise e

def get_rois_by_width(width):
    if width >= 2500:
        return RESOLUTION_MAP[2560]
    return RESOLUTION_MAP[1920]

def is_screen_changed(img1, img2, threshold=1000):
    if img1 is None or img2 is None: return True
    if img1.shape != img2.shape: return True

    h, w = img1.shape[:2]
    small_h, small_w = max(1, h//10), max(1, w//10)
    
    small1 = cv2.resize(img1, (small_w, small_h), interpolation=cv2.INTER_NEAREST)
    small2 = cv2.resize(img2, (small_w, small_h), interpolation=cv2.INTER_NEAREST)

    gray1 = cv2.cvtColor(small1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(small2, cv2.COLOR_BGR2GRAY)
    diff = cv2.absdiff(gray1, gray2)
    
    sensitive_threshold = max(5, threshold // 100)
    non_zero_count = np.count_nonzero(diff > 30)
    return non_zero_count > sensitive_threshold

def normalize_text(text):
    """특수문자 제거 및 정규화"""
    return re.sub(r'[^\w가-힣\s]', '', text).strip()

# =========================
# OCR 함수 (PaddleOCR / Tesseract)
# =========================
def extract_title_text(full_img, roi_coords):
    x1, y1, x2, y2 = roi_coords
    h, w, _ = full_img.shape
    if x2 > w or y2 > h: return ""

    roi = full_img[y1:y2, x1:x2]
    if roi.size == 0: return ""

    if USE_PADDLE:
        # PaddleOCR 사용
        try:
            # PaddleOCR은 파일 경로 또는 numpy array를 받음
            # numpy array를 직접 넘기면 됨
            output = OCR_MODEL.predict(input=roi, batch_size=1)
            for res in output:
                # res는 dict-like 객체
                text = res.get("rec_text", "") if hasattr(res, 'get') else ""
                # res가 객체라면 속성 접근
                if not text and hasattr(res, 'rec_text'):
                    text = res.rec_text
                return normalize_text(text)
        except Exception as e:
            print(f"[Watcher] PaddleOCR Error: {e}")
            return ""
    else:
        # Tesseract Fallback
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        height, width = binary.shape
        binary = cv2.resize(binary, (width * 2, height * 2), interpolation=cv2.INTER_CUBIC)
        text = pytesseract.image_to_string(binary, lang='kor', config="--psm 7")
        return normalize_text(text)

def extract_three_titles(full_img):
    h, w, _ = full_img.shape
    target_rois = get_rois_by_width(w)

    raw_titles = []
    for roi in target_rois:
        text = extract_title_text(full_img, roi)
        if len(text) > 1:
            raw_titles.append(text)
    
    if len(raw_titles) != 3: return []

    valid_count = sum(1 for t in raw_titles if is_valid_text(t))
    return raw_titles if valid_count >= 2 else []

# =========================
# Watcher Class
# =========================
class AugmentWatcher:
    def __init__(self):
        self._stop_event = threading.Event()
        self._thread = None
        self.last_img = None 
        self.last_candidates = []
        self.stability_count = 0
        self.required_stability = 2 
        self.last_sent_titles = []
        self.last_sent_time = 0
        self.cached_titles = []

    def start(self):
        load_valid_names()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop)
        self._thread.daemon = True
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join()

    def _loop(self):
        ocr_type = "PaddleOCR" if USE_PADDLE else "Tesseract"
        print(f"[Watcher] OCR Monitoring started ({ocr_type})...")
        error_count = 0
        
        with mss.mss() as sct:
            while not self._stop_event.is_set():
                try:
                    time.sleep(POLL_INTERVAL)
                    
                    try:
                        full_img = grab_screen_bgr(sct)
                    except Exception:
                        time.sleep(1)
                        continue

                    has_changed = is_screen_changed(self.last_img, full_img)
                    self.last_img = full_img 

                    if has_changed:
                        titles = extract_three_titles(full_img)
                        self.cached_titles = titles 
                    else:
                        titles = self.cached_titles

                    if not titles:
                        self.stability_count = 0
                        self.last_candidates = []
                        
                        if self.last_sent_titles:
                             print("[Watcher] Augments disappeared.")
                             self._send_inactive()
                             self.last_sent_titles = [] 
                             self.cached_titles = []
                        continue
                    
                    if titles == self.last_candidates:
                        self.stability_count += 1
                    else:
                        self.stability_count = 1
                        self.last_candidates = titles
                    
                    if self.stability_count >= self.required_stability:
                        if (titles != self.last_sent_titles) or (time.time() - self.last_sent_time > 3.0):
                            print(f"[Watcher] Detected: {titles}")
                            self._send_titles(titles)
                            self.last_sent_titles = titles
                            self.last_sent_time = time.time()
                            self._smart_sleep(2.0, sct)
                            error_count = 0 

                except Exception as e:
                    error_count += 1
                    if error_count % 10 == 0:
                        print(f"[Watcher] Loop Error: {e}")
                    time.sleep(1)

    def _smart_sleep(self, duration, sct):
        check_interval = 0.2
        steps = int(duration / check_interval)
        
        for _ in range(steps):
            if self._stop_event.is_set(): break
            time.sleep(check_interval)
            
            try:
                current_img = grab_screen_bgr(sct)
                if is_screen_changed(self.last_img, current_img):
                    print("[Watcher] Reroll detected! Waking up...")
                    break 
            except:
                break

    def _send_titles(self, titles):
        try:
            requests.post("http://127.0.0.1:5000/augments/update", json={
                "active": True, "names_ko": titles, "champion": "" 
            })
        except: pass

    def _send_inactive(self):
        if self.last_sent_titles == []: return
        try:
            requests.post("http://127.0.0.1:5000/augments/update", json={"active": False})
            self.last_sent_titles = []
        except: pass

if __name__ == "__main__":
    watcher = AugmentWatcher()
    watcher.start()
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        watcher.stop()