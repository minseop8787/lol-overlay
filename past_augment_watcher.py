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

# ✅ Tesseract 경로 (배포 시 사용자에게 설치 안내 필요)
# 혹은 포터블 버전을 프로젝트에 포함시키고 resource_path로 지정하는 방법도 있음
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# =========================
# PATH & SETTINGS (배포용 수정됨)
# =========================

# ✅ [수정됨] 경로 설정 함수 (PyInstaller 환경 대응)
def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# =========================
# Tesseract 경로 설정 (포터블 우선)
# =========================
# 1. 내장된(포터블) 테서렉트 경로를 먼저 찾음
portable_tesseract = resource_path(os.path.join("Tesseract-OCR", "tesseract.exe"))

# 2. 내장된 게 있으면 그거 쓰고, 없으면(개발환경 등) 시스템 설치 경로 사용
if os.path.exists(portable_tesseract):
    pytesseract.pytesseract.tesseract_cmd = portable_tesseract
    print(f"[Watcher] Using Portable Tesseract: {portable_tesseract}")
else:
    # 혹시 모르니 시스템 경로도 남겨둠 (개발용)
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    print("[Watcher] Using System Tesseract")

# [수정] resource_path를 사용하여 경로 설정
MAPPING_TXT_PATH = Path(resource_path("augment_mapping_full.txt"))

# OCR 설정
POLL_INTERVAL = 0.2       # 감지 주기
OCR_LANG = "kor"          # 한글 인식

# [좌표 설정] 1920x1080 기준
CARD_TOP_Y = 180
CARD_BOT_Y = 707

LEFT_CARD_X1,  LEFT_CARD_X2  = 449, 760
MID_CARD_X1,   MID_CARD_X2   = 806, 1108
RIGHT_CARD_X1, RIGHT_CARD_X2 = 1160, 1462

# 카드 내 제목 위치 (경험적 수치)
TITLE_ROI_Y1 = 232
TITLE_ROI_Y2 = 267
TITLE_ROI_MARGIN_X = 15 

# =========================
# 데이터 로드 (화이트리스트)
# =========================
VALID_NAMES = []

def load_valid_names():
    """매핑 파일에서 유효한 한글 증강 이름들을 메모리에 로드"""
    global VALID_NAMES
    
    # Path 객체 호환성 체크
    path_obj = MAPPING_TXT_PATH
    if not os.path.exists(path_obj):
        print(f"[Watcher] Warning: {path_obj} not found in resources. Strict check disabled.")
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
    """읽은 텍스트가 유효한 증강 이름인지 확인 (유사도 검사)"""
    if not VALID_NAMES:
        return True # 파일 없으면 그냥 통과
    
    # 정확히 일치하면 통과
    if text in VALID_NAMES:
        return True
        
    # 약간 틀렸어도(오타) 비슷하면 통과 (cutoff=0.6: 60% 이상 유사)
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
    text = pytesseract.image_to_string(processed, lang=OCR_LANG, config="--psm 7")
    text = re.sub(r"[^\w가-힣\s]", "", text).strip()
    return text

def extract_three_titles(full_img):
    t1 = extract_title_text(full_img, LEFT_CARD_X1, LEFT_CARD_X2)
    t2 = extract_title_text(full_img, MID_CARD_X1, MID_CARD_X2)
    t3 = extract_title_text(full_img, RIGHT_CARD_X1, RIGHT_CARD_X2)
    
    raw_titles = [t for t in [t1, t2, t3] if len(t) > 1]
    
    if len(raw_titles) != 3:
        return []

    valid_count = 0
    for t in raw_titles:
        if is_valid_text(t):
            valid_count += 1
            
    if valid_count >= 2: 
        return raw_titles
    else:
        return [] 

# =========================
# Watcher Class
# =========================
class AugmentWatcher:
    def __init__(self):
        self._stop_event = threading.Event()
        self._thread = None
        
        self.last_candidates = []
        self.stability_count = 0
        self.required_stability = 2 
        
        self.last_sent_titles = []
        self.last_sent_time = 0

    def start(self):
        load_valid_names() # 시작할 때 이름 목록 로드 (경로 수정됨)
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop)
        self._thread.daemon = True
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join()

    def _loop(self):
        print("[Watcher] OCR Monitoring started (Robust Mode)...")
        error_count = 0
        
        while not self._stop_event.is_set():
            try:
                # 0.5초마다 체크 (CPU 절약)
                time.sleep(POLL_INTERVAL)
                
                # 스크린샷 시도 (여기서 가끔 에러남)
                try:
                    full_img = grab_screen_bgr()
                except Exception as e:
                    print(f"[Watcher] Screen Grab Error: {e}")
                    time.sleep(1)
                    continue

                titles = extract_three_titles(full_img)
                
                # 1. 화면에 증강이 없을 때
                if not titles:
                    self.stability_count = 0
                    self.last_candidates = []
                    
                    # 카드가 사라지면 즉시(0초) 리셋 신호 보냄
                    # (2~3분 뒤 두 번째 증강을 위해 상태를 깨끗이 비움)
                    if self.last_sent_titles:
                         print("[Watcher] Augments disappeared. Resetting state.")
                         self._send_inactive()
                         self.last_sent_titles = [] # 확실하게 비우기
                    continue
                
                # 2. 증강이 감지됨 (흔들림 보정)
                if titles == self.last_candidates:
                    self.stability_count += 1
                else:
                    self.stability_count = 1
                    self.last_candidates = titles
                
                # 3. 데이터 전송 (안정화됨)
                if self.stability_count >= self.required_stability:
                    # 새로운 내용이거나, 기존 내용이라도 3초마다 한 번씩 갱신(리마인드)
                    if (titles != self.last_sent_titles) or (time.time() - self.last_sent_time > 3.0):
                        print(f"[Watcher] Valid Augments Detected: {titles}")
                        self._send_titles(titles)
                        self.last_sent_titles = titles
                        self.last_sent_time = time.time()
                        error_count = 0 # 성공하면 에러 카운트 초기화

            except Exception as e:
                # 치명적인 에러가 나도 죽지 않고 살아남기
                error_count += 1
                if error_count % 10 == 0: # 로그 너무 많이 뜨지 않게
                    print(f"[Watcher] Critical Loop Error: {e}")
                time.sleep(1)

    def _send_titles(self, titles):
        try:
            requests.post("http://127.0.0.1:5000/augments/update", json={
                "active": True,
                "names_ko": titles,
                "champion": "" 
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