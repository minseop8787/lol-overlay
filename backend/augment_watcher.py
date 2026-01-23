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

# 🔥 [최적화] 반응 속도를 위해 0.2초로 단축
POLL_INTERVAL = 0.2       

# =========================
# 📐 해상도별 좌표 설정 (ROI: x1, y1, x2, y2)
# =========================
# 기존 1920 좌표는 '카드위치 + 마진' 계산을 미리 수행하여 절대 좌표로 변환함
RESOLUTION_MAP = {
    # [기본] 1920x1080
    # 계산식: Y=180+232~180+267, X=카드좌표 ± 15(마진)
    1920: [
        (474, 412, 740, 447),   # 왼쪽
        (824, 412, 1093, 447),  # 중간
        (1180, 412, 1447, 447)  # 오른쪽
    ],
    # [친구] 2560x1080 (울트라와이드)
    # 친구분이 제공한 좌표 그대로 적용
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
# =========================
# 이미지 처리 함수들
# =========================
def grab_screen_bgr(sct):
    # 주 모니터 감지
    monitor = sct.monitors[1]
    img = np.array(sct.grab(monitor))
    return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

def get_rois_by_width(width):
    if width >= 2500:
        return RESOLUTION_MAP[2560]
    return RESOLUTION_MAP[1920]

# 🔥 화면 변화 감지 (가벼운 연산)
def is_screen_changed(img1, img2, rois=None, threshold=1000):
    if img1 is None or img2 is None: return True
    
    # 해상도가 다르면(게임 중 해상도 변경 등) 무조건 변경된 것으로 처리
    if img1.shape != img2.shape: return True

    # ROI가 주어지면 해당 영역만 비교 (증강체 위치만 감시)
    if rois:
        changed_pixels = 0
        for (x1, y1, x2, y2) in rois:
            # 안전장치
            h, w, _ = img1.shape
            if x2 > w or y2 > h: continue

            c1 = img1[y1:y2, x1:x2]
            c2 = img2[y1:y2, x1:x2]
            
            gray1 = cv2.cvtColor(c1, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(c2, cv2.COLOR_BGR2GRAY)
            
            diff = cv2.absdiff(gray1, gray2)
            changed_pixels += np.count_nonzero(diff > 30)
            
            if changed_pixels > threshold:
                return True
        return False

    # 기존 전체 화면 비교 (Fallback)
    gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
    
    # 1/4 리사이즈로 비교 속도 극대화
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
        self.sct = mss.mss() # 🔥 MSS 인스턴스 재사용
        
        # 🔥 [최적화 2] OCR 결과 캐싱용 변수
        self.cached_titles = []
        
        # 🔥 [신규] 버튼 감지 템플릿 로드
        self.btn_template = None
        try:
            # backend/templates/augment_confirm_button.png
            btn_path = resource_path(os.path.join("templates", "augment_confirm_button.png"))
            if os.path.exists(btn_path):
                self.btn_template = cv2.imread(btn_path, cv2.IMREAD_COLOR)
                print(f"[Watcher] Button template loaded: {btn_path}")
            else:
                print(f"[Watcher] ⚠️ Button template NOT found: {btn_path}")
        except Exception as e:
            print(f"[Watcher] Error loading button template: {e}")

    def is_button_visible(self, full_img):
        if self.btn_template is None: return True # 템플릿 없으면 항상 True (기존 로직이나 항상 OCR 돌림)
        
        h, w, _ = full_img.shape
        # 버튼이 뜰만한 위치 (하단 중앙) ROI 설정
        # (대략적인 위치를 잡아서 매칭 속도 등 최적화)
        
        # 1920x1080 기준: X=(960-100)~(960+100), Y=(800-1000) 정도
        # 버튼은 보통 (840, 720) ~ (1080, 780) 사이에 위치함 (리롤버튼 등)
        # 넉넉하게 잡음: 중앙 하단 1/4 영역
        
        roi_y = int(h * 0.6)
        roi_h = int(h * 0.3) # 60% ~ 90% 높이 검색
        roi_x = int(w * 0.3)
        roi_w = int(w * 0.4) # 중앙 40% 너비
        
        roi = full_img[roi_y:roi_y+roi_h, roi_x:roi_x+roi_w]
        
        # 템플릿 매칭
        res = cv2.matchTemplate(roi, self.btn_template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        
        # 임계값: 버튼이 명확하므로 0.8 이상이면 충분
        return max_val > 0.8

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
        # 스레드 종료 후 MSS 닫기
        try:
            self.sct.close() 
        except: pass

    def _loop(self):
        print("[Watcher] OCR Monitoring started (Optimized)...")
        error_count = 0
        
        while not self._stop_event.is_set():
            try:
                # 0.2초 대기 (반응 속도 향상)
                time.sleep(POLL_INTERVAL)
                
                try:
                    full_img = grab_screen_bgr(self.sct)
                except:
                    time.sleep(1)
                    continue

                # 해상도에 따른 ROI 가져오기 (OCR용)
                h, w, _ = full_img.shape
                current_rois = get_rois_by_width(w)

                # 🔥 [수정] 화면 변화 감지 대신, '증강 선택 버튼(파란색 리롤 버튼 등)'이 떠있는지 확인
                is_active = self.is_button_visible(full_img)

                if is_active:
                    # 버튼이 보이면 증강 선택 창임 -> OCR 실행
                    titles = extract_three_titles(full_img)
                    self.cached_titles = titles 
                else:
                    # 버튼이 안보이면 증강 창 아님
                    titles = []
                    self.cached_titles = []

                # --- 이하 로직 동일 ---

                # A. 증강체 없음
                if not titles:
                    self.stability_count = 0
                    self.last_candidates = []
                    
                    if self.last_sent_titles:
                         print("[Watcher] Augments disappeared (Button hidden).")
                         self._send_inactive()
                         self.last_sent_titles = [] 
                         self.cached_titles = [] 
                    continue

                # --- 이하 로직 동일 ---

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

    # 리롤 감시하며 쉬기
    def _smart_sleep(self, duration):
        check_interval = 0.2
        steps = int(duration / check_interval)
        
        for _ in range(steps):
            if self._stop_event.is_set(): break
            time.sleep(check_interval)
            
            try:
                current_img = grab_screen_bgr(self.sct)
                # 쉬는 도중 화면이 바뀌면(=리롤) 즉시 기상 (여기도 ROI 체크가 좋지만 리롤은 전체가 바뀔수도 있음)
                # 리롤 버튼 위치만 볼 수도 있지만, 일단 전체 변화 체크가 더 확실할 수 있음. 
                # 하지만 성능을 위해 ROI 체크를 우선 시도해봄.
                
                h, w, _ = current_img.shape
                rois = get_rois_by_width(w)

                if is_screen_changed(self.last_img, current_img, rois=rois):
                    print("[Watcher] Reroll detected (ROI changed)! Waking up...")
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