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
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# Tesseract Setup
portable_tesseract = resource_path(os.path.join("Tesseract-OCR", "tesseract.exe"))
if os.path.exists(portable_tesseract):
    pytesseract.pytesseract.tesseract_cmd = portable_tesseract
    print(f"[Watcher] Using Portable Tesseract: {portable_tesseract}")
else:
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    print("[Watcher] Using System Tesseract (Dev Check)")

# Data Files
MAPPING_TXT_PATH = resource_path("augment_mapping_full.txt")
BUTTON_TEMPLATE_PATH = resource_path("assets/augment_confirm_button.png")

BUTTON_TEMPLATE = cv2.imread(BUTTON_TEMPLATE_PATH)
if BUTTON_TEMPLATE is None:
    print(f"[Watcher] Warning: Button template not found at {BUTTON_TEMPLATE_PATH}")
else:
    print("[Watcher] Button template loaded.")

# Config
POLL_INTERVAL = 0.2
OCR_LANG = "kor"

# ROI Coordinates (1920x1080)
# Cards X
LEFT_CARD_X1,  LEFT_CARD_X2  = 449, 760
MID_CARD_X1,   MID_CARD_X2   = 806, 1108
RIGHT_CARD_X1, RIGHT_CARD_X2 = 1160, 1462
# Card Y
CARD_TOP_Y = 180
# Title Relative Y
TITLE_ROI_Y1 = 232
TITLE_ROI_Y2 = 267
TITLE_ROI_MARGIN_X = 15 

VALID_NAMES = []
ENG_TO_KOR = {} # OCR 결과 검증용

def load_valid_names():
    global VALID_NAMES
    if not os.path.exists(MAPPING_TXT_PATH):
        print(f"[Watcher] Warning: {MAPPING_TXT_PATH} not found.")
        return

    names = set()
    try:
        with open(MAPPING_TXT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    ko, _ = line.split("=", 1)
                    names.add(ko.strip())
                elif " : " in line:
                    ko, _ = line.split(" : ", 1)
                    names.add(ko.strip())
        VALID_NAMES = list(names)
        print(f"[Watcher] Loaded {len(VALID_NAMES)} valid names from mapping file.")
    except Exception as e:
        print(f"[Watcher] Error loading mapping: {e}")

def is_valid_text(text):
    if not VALID_NAMES: return True
    if text in VALID_NAMES: return True
    matches = difflib.get_close_matches(text, VALID_NAMES, n=1, cutoff=0.6)
    return len(matches) > 0

def clean_text(text):
    # 특수문자 제거하고 한글/영문/숫자만 남김
    return re.sub(r"[^\w가-힣\s]", "", text).strip()

def preprocess_for_ocr(img_roi):
    # 2배 확대 + Otsu 이진화
    gray = cv2.cvtColor(img_roi, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    h, w = binary.shape
    binary = cv2.resize(binary, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
    return binary

def extract_title_text(full_img, x1, x2):
    # 좌표 계산
    y1_abs = CARD_TOP_Y + TITLE_ROI_Y1
    y2_abs = CARD_TOP_Y + TITLE_ROI_Y2
    x1_abs = x1 + TITLE_ROI_MARGIN_X
    x2_abs = x2 - TITLE_ROI_MARGIN_X
    
    roi = full_img[y1_abs:y2_abs, x1_abs:x2_abs]
    if roi.size == 0: return ""
    
    processed = preprocess_for_ocr(roi)
    # Tesseract 실행 --psm 7 (Single Line)
    try:
        raw_text = pytesseract.image_to_string(processed, lang=OCR_LANG, config="--psm 7")
        text = clean_text(raw_text)
        return text
    except Exception as e:
        print(f"[Watcher] OCR Fail: {e}")
        return ""

def extract_three_titles(full_img):
    t1 = extract_title_text(full_img, LEFT_CARD_X1, LEFT_CARD_X2)
    t2 = extract_title_text(full_img, MID_CARD_X1, MID_CARD_X2)
    t3 = extract_title_text(full_img, RIGHT_CARD_X1, RIGHT_CARD_X2)
    
    # 3개 중 2개 이상이 유효하면 성공
    raw_titles = [t for t in [t1, t2, t3] if len(t) > 1]
    if len(raw_titles) < 2: return []
    
    return raw_titles

class AugmentWatcher:
    def __init__(self):
        self._stop_event = threading.Event()
        self._thread = None
        self.last_sent_titles = []
        self.last_sent_time = 0
        self.stability_count = 0
        self.last_candidates = []

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
        print("[Watcher] OCR Monitoring started...")
        with mss.mss() as sct:
            while not self._stop_event.is_set():
                time.sleep(POLL_INTERVAL)
                try:
                    # 화면 캡처
                    monitor = sct.monitors[1]
                    img = np.array(sct.grab(monitor))
                    full_img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                    
                    title_titles = extract_three_titles(full_img)
                    
                    # [추가] 증강 선택창인지 확실하게 확인 (Confirm Button Check)
                    # 좌표: 858, 825 ~ 1060, 890
                    btn_roi = full_img[825:890, 858:1060]
                    is_augment_phase = False
                    
                    if BUTTON_TEMPLATE is not None:
                        # 템플릿 매칭
                        res = cv2.matchTemplate(btn_roi, BUTTON_TEMPLATE, cv2.TM_CCOEFF_NORMED)
                        _, max_val, _, _ = cv2.minMaxLoc(res)
                        
                        # 사용자 요청: 유사도 0.85 이상일 때만 인정
                        if max_val >= 0.85:
                            is_augment_phase = True
                        else:
                            # 버튼이 없으면 OCR 결과가 있어도 무시 (오인식 방지)
                            # print(f"[Watcher] Button Score: {max_val:.2f} (Required: 0.85)")
                            pass
                    else:
                        # 템플릿 파일이 없으면 그냥 OCR 결과만 믿음 (기존 동작)
                        is_augment_phase = True

                    if not is_augment_phase or not title_titles:
                        # 리셋 로직
                        self.stability_count = 0
                        if self.last_sent_titles:
                            # print("[Watcher] Cleared (No Button or Titles).")
                            self._send_update(active=False)
                            self.last_sent_titles = []
                        continue

                    # 안정화 (흔들림 방지, 2회 연속 일치)
                    if title_titles == self.last_candidates:
                        self.stability_count += 1
                    else:
                        self.stability_count = 1
                        self.last_candidates = title_titles
                    
                    if self.stability_count >= 2:
                        # 중복 전송 방지 (3초 쿨타임)
                        if (title_titles != self.last_sent_titles) or (time.time() - self.last_sent_time > 3.0):
                            print(f"[Watcher] Detect: {title_titles}")
                            self._send_update(active=True, titles=title_titles)
                            self.last_sent_titles = title_titles
                            self.last_sent_time = time.time()
                            
                except Exception as e:
                    print(f"[Watcher] Error: {e}")
                    time.sleep(1)

    def _send_update(self, active, titles=None):
        try:
            data = {"active": active}
            if active and titles:
                data["names_ko"] = titles
            requests.post("http://127.0.0.1:5000/augments/update", json=data)
        except: pass

if __name__ == "__main__":
    w = AugmentWatcher()
    w.start()
    while True: time.sleep(1)