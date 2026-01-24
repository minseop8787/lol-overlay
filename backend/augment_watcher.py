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
import pytesseract
import requests

# =========================
# PATH & SETTINGS
# =========================

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

# Tesseract 경로 설정
portable_tesseract = resource_path(os.path.join("Tesseract-OCR", "tesseract.exe"))
if os.path.exists(portable_tesseract):
    pytesseract.pytesseract.tesseract_cmd = portable_tesseract
    print(f"[Watcher] Using Portable Tesseract: {portable_tesseract}")
else:
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    print("[Watcher] Using System Tesseract")

MAPPING_TXT_PATH = Path(resource_path("augment_mapping_full.txt"))

# 🔥 [최적화] 반응 속도를 위해 0.2초로 단축
POLL_INTERVAL = 0.2       

# =========================
# 📐 해상도별 좌표 설정 (ROI: x1, y1, x2, y2)
# =========================
RESOLUTION_MAP = {
    # [기본] 1920x1080
    1920: [
        (474, 412, 740, 447),   # 왼쪽
        (824, 412, 1093, 447),  # 중간
        (1180, 412, 1447, 447)  # 오른쪽
    ],
    # [친구] 2560x1080 (울트라와이드)
    2560: [
        (789, 410, 1063, 448),  # 왼쪽
        (1143, 414, 1413, 446), # 중간
        (1500, 413, 1767, 447)  # 오른쪽
    ]
}

VALID_NAMES = []

def load_valid_names():
    global VALID_NAMES
    path_obj = MAPPING_TXT_PATH
    if not os.path.exists(path_obj):
        return

    names = set()
    try:
        with open(path_obj, "r", encoding="utf-8") as f:
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
    # 주 모니터 감지 logic 개선
    try:
        if len(sct.monitors) > 1:
            monitor = sct.monitors[1]
        else:
            monitor = sct.monitors[0] # 모니터가 하나뿐인 경우
            
        img = np.array(sct.grab(monitor))
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    except Exception as e:
        # print(f"[Watcher] Screen Grab Error: {e}") # 너무 시끄러울 수 있음
        raise e

def get_rois_by_width(width):
    if width >= 2500:
        return RESOLUTION_MAP[2560]
    return RESOLUTION_MAP[1920]

# 🔥 화면 변화 감지 (가벼운 연산)
def is_screen_changed(img1, img2, threshold=1000):
    if img1 is None or img2 is None: return True
    
    # 해상도가 다르면 무조건 변경
    if img1.shape != img2.shape: return True

    # 🔥 [수정] 1/10 리사이즈로 초고속 비교
    h, w = img1.shape[:2]
    small_h, small_w = max(1, h//10), max(1, w//10)
    
    small1 = cv2.resize(img1, (small_w, small_h), interpolation=cv2.INTER_NEAREST)
    small2 = cv2.resize(img2, (small_w, small_h), interpolation=cv2.INTER_NEAREST)

    gray1 = cv2.cvtColor(small1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(small2, cv2.COLOR_BGR2GRAY)

    diff = cv2.absdiff(gray1, gray2)
    # 리사이즈 했으므로 임계값도 조정해야 함 (픽셀 수가 1/100로 줄었으므로)
    # 기존 threshold가 1000이라면 10 정도로 줄여야 함
    sensitive_threshold = max(5, threshold // 100) 
    
    non_zero_count = np.count_nonzero(diff > 30)
    return non_zero_count > sensitive_threshold

def preprocess_for_ocr(img_roi):
    gray = cv2.cvtColor(img_roi, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    height, width = binary.shape
    binary = cv2.resize(binary, (width * 2, height * 2), interpolation=cv2.INTER_CUBIC)
    return binary

def extract_title_text(full_img, roi_coords):
    x1, y1, x2, y2 = roi_coords
    
    # 이미지 범위 체크 (안전장치)
    h, w, _ = full_img.shape
    if x2 > w or y2 > h: return ""

    roi = full_img[y1:y2, x1:x2]
    if roi.size == 0: return ""
    
    processed = preprocess_for_ocr(roi)
    text = pytesseract.image_to_string(processed, lang='kor', config="--psm 7")
    text = re.sub(r"[^\w가-힣\s]", "", text).strip()
    return text

def extract_three_titles(full_img):
    # 1. 현재 화면의 너비 확인
    h, w, _ = full_img.shape
    
    # 2. 너비에 따른 좌표 선택
    target_rois = get_rois_by_width(w)

    raw_titles = []
    # 3. 3개의 좌표(왼쪽, 중간, 오른쪽)를 순회하며 OCR 수행
    for roi in target_rois:
        text = extract_title_text(full_img, roi)
        if len(text) > 1:
            raw_titles.append(text)
    
    if len(raw_titles) != 3: return []

    valid_count = 0
    for t in raw_titles:
        if is_valid_text(t): valid_count += 1
    
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
        print("[Watcher] OCR Monitoring started (Optimized)...")
        error_count = 0
        
        # 🔥 [핵심 1] MSS 객체를 스레드 내에서 한 번만 생성하여 사용
        with mss.mss() as sct:
            while not self._stop_event.is_set():
                try:
                    time.sleep(POLL_INTERVAL)
                    
                    # 1. 화면 캡처
                    try:
                        full_img = grab_screen_bgr(sct)
                    except Exception:
                        time.sleep(1)
                        continue

                    # 2. 화면 변화 감지
                    has_changed = is_screen_changed(self.last_img, full_img)
                    self.last_img = full_img 

                    # 3. OCR 수행 여부 결정
                    if has_changed:
                        titles = extract_three_titles(full_img)
                        self.cached_titles = titles 
                    else:
                        titles = self.cached_titles

                    # 4. 데이터 안정화 및 전송 로직 (기존과 동일)
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
                            
                            # 전송 성공 후 잠시 대기
                            self._smart_sleep(2.0, sct)
                            error_count = 0 

                except Exception as e:
                    # 🔥 [핵심 2] 무한 루프 사망 방지
                    error_count += 1
                    if error_count % 10 == 0:
                        print(f"[Watcher] Loop Error: {e}")
                    time.sleep(1)

    # 리롤 감시하며 쉬기 (sct 객체 전달받음)
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