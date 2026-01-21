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
    return os.path.join(os.path.abspath("."), relative_path)

# Tesseract 경로 설정
portable_tesseract = resource_path(os.path.join("Tesseract-OCR", "tesseract.exe"))
if os.path.exists(portable_tesseract):
    pytesseract.pytesseract.tesseract_cmd = portable_tesseract
    print(f"[Watcher] Using Portable Tesseract: {portable_tesseract}")
else:
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    print("[Watcher] Using System Tesseract")

MAPPING_TXT_PATH = Path(resource_path("augment_mapping_full.txt"))

# 🔥 [최적화 1] 반응 속도를 위해 0.2초로 단축 (CPU 최적화 덕분에 괜찮음)
POLL_INTERVAL = 0.2       

# [좌표 설정]
CARD_TOP_Y = 180
CARD_BOT_Y = 707
LEFT_CARD_X1,  LEFT_CARD_X2  = 449, 760
MID_CARD_X1,   MID_CARD_X2   = 806, 1108
RIGHT_CARD_X1, RIGHT_CARD_X2 = 1160, 1462

TITLE_ROI_Y1 = 232
TITLE_ROI_Y2 = 267
TITLE_ROI_MARGIN_X = 15 

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
def grab_screen_bgr():
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        img = np.array(sct.grab(monitor))
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

# 🔥 화면 변화 감지 (가벼운 연산)
def is_screen_changed(img1, img2, threshold=1000):
    if img1 is None or img2 is None: return True
    
    gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
    
    # 1/4 리사이즈로 속도 극대화
    small1 = cv2.resize(gray1, (0,0), fx=0.25, fy=0.25)
    small2 = cv2.resize(gray2, (0,0), fx=0.25, fy=0.25)

    diff = cv2.absdiff(small1, small2)
    non_zero_count = np.count_nonzero(diff > 30)
    
    return non_zero_count > threshold

def preprocess_for_ocr(img_roi):
    gray = cv2.cvtColor(img_roi, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    height, width = binary.shape
    binary = cv2.resize(binary, (width * 2, height * 2), interpolation=cv2.INTER_CUBIC)
    return binary

def extract_title_text(full_img, card_x1, card_x2):
    y1 = CARD_TOP_Y + TITLE_ROI_Y1
    y2 = CARD_TOP_Y + TITLE_ROI_Y2
    x1 = card_x1 + TITLE_ROI_MARGIN_X
    x2 = card_x2 - TITLE_ROI_MARGIN_X
    
    roi = full_img[y1:y2, x1:x2]
    if roi.size == 0: return ""
    
    processed = preprocess_for_ocr(roi)
    text = pytesseract.image_to_string(processed, lang='kor', config="--psm 7")
    text = re.sub(r"[^\w가-힣\s]", "", text).strip()
    return text

def extract_three_titles(full_img):
    t1 = extract_title_text(full_img, LEFT_CARD_X1, LEFT_CARD_X2)
    t2 = extract_title_text(full_img, MID_CARD_X1, MID_CARD_X2)
    t3 = extract_title_text(full_img, RIGHT_CARD_X1, RIGHT_CARD_X2)
    
    raw_titles = [t for t in [t1, t2, t3] if len(t) > 1]
    
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
        
        # 🔥 [최적화 2] OCR 결과 캐싱용 변수
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
        print("[Watcher] OCR Monitoring started (Fast & Optimized)...")
        error_count = 0
        
        while not self._stop_event.is_set():
            try:
                # 0.2초 대기 (반응 속도 향상)
                time.sleep(POLL_INTERVAL)
                
                try:
                    full_img = grab_screen_bgr()
                except:
                    time.sleep(1)
                    continue

                # 화면 변화 체크
                has_changed = is_screen_changed(self.last_img, full_img)
                
                # 현재 화면 저장 (다음 비교를 위해)
                self.last_img = full_img 

                if has_changed:
                    # 🔥 화면이 바뀌었을 때만 무거운 OCR 실행!
                    titles = extract_three_titles(full_img)
                    self.cached_titles = titles # 결과 저장(캐싱)
                else:
                    # 🔥 화면이 안 바뀌었으면? 아까 읽은 거 그대로 씀 (CPU 0% 사용)
                    # 이렇게 해야 '안정화 카운트'가 쭉쭉 올라가서 바로 전송됨
                    titles = self.cached_titles

                # --- 이하 로직은 동일하지만, 위 캐싱 덕분에 매끄럽게 작동함 ---

                # A. 증강체 없음
                if not titles:
                    self.stability_count = 0
                    self.last_candidates = []
                    
                    if self.last_sent_titles:
                         print("[Watcher] Augments disappeared.")
                         self._send_inactive()
                         self.last_sent_titles = [] 
                         self.cached_titles = [] # 캐시도 비움
                    continue
                
                # B. 증강체 감지됨
                if titles == self.last_candidates:
                    self.stability_count += 1
                else:
                    self.stability_count = 1
                    self.last_candidates = titles
                
                # C. 데이터 전송
                if self.stability_count >= self.required_stability:
                    if (titles != self.last_sent_titles) or (time.time() - self.last_sent_time > 3.0):
                        print(f"[Watcher] Detected: {titles}")
                        self._send_titles(titles)
                        self.last_sent_titles = titles
                        self.last_sent_time = time.time()
                        
                        # 전송 성공 후 리롤 감시하며 대기
                        self._smart_sleep(2.0)
                        
                        error_count = 0 

            except Exception as e:
                error_count += 1
                if error_count % 10 == 0:
                    print(f"[Watcher] Loop Error: {e}")
                time.sleep(1)

    # 리롤 감지하며 쉬기
    def _smart_sleep(self, duration):
        check_interval = 0.2
        steps = int(duration / check_interval)
        
        for _ in range(steps):
            if self._stop_event.is_set(): break
            time.sleep(check_interval)
            
            try:
                current_img = grab_screen_bgr()
                # 쉬는 도중 화면이 바뀌면(=리롤) 즉시 기상
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