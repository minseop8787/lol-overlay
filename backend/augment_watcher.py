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

                # 해상도에 따른 ROI 가져오기
                h, w, _ = full_img.shape
                current_rois = get_rois_by_width(w)

                # 화면 변화 체크 (ROI만)
                # 🔥 [수정] 임계값 1000 -> 200으로 대폭 낮춤 (작은 글씨 변화 감지)
                has_changed = is_screen_changed(self.last_img, full_img, rois=current_rois, threshold=200)
                
                # 현재 화면 저장 (다음 비교를 위해)
                self.last_img = full_img 
                
                # 🔥 [수정] 안전장치: 화면이 안 바뀌더라도, 결과가 없으면 가끔 한 번씩 재검사 (1초마다)
                # 이는 초기 진입 시 이미 증강이 떠있는 상태라 변화 감지가 안되는 경우를 방지함
                force_check = False
                if not self.cached_titles and (time.time() - self.last_sent_time > 1.0):
                     # 단, last_sent_time은 전송 시간이라 적절치 않음. 루프 내 별도 타이머 필요.
                     # 여기선 간단히 5번 루프(약 1초)마다 강제 검사하도록 로직 변경 필요하지만,
                     # 가장 확실한 건 "캐시가 비어있으면" 변화 여부 상관없이 1초에 한번씩 훑는 것.
                     pass

                # 로직 개선: 
                # 1. 변화 감지됨 -> 즉시 OCR
                # 2. 변화 없음 & 캐시 있음 -> 캐시 유지 (성공)
                # 3. 변화 없음 & 캐시 없음 -> 1초마다 강제 재확인 (혹시 놓쳤을까봐)
                
                current_time = time.time()
                
                # 마지막 강제 체크 시간 (루프 밖 __init__에 있어야 하지만 여기서 임시 처리 위해 전역 변수처럼 사용 불가)
                # 따라서 로직을 단순화:
                # "변화가 있거나" OR ("캐시가 비었고" AND "임의 확률로")
                
                # 5번에 1번 꼴로(약 1초) 강제 리프레시
                should_force_refresh = (not self.cached_titles) and (int(current_time * 10) % 10 == 0)

                if has_changed or should_force_refresh:
                    # if should_force_refresh: print("[Watcher] Failsafe checking...")
                    titles = extract_three_titles(full_img)
                    
                    # 🔥 [중요] 읽힌 게 있을 때만 캐시를 갱신해야 함?
                    # 아님. 읽힌 게 없으면 없는 대로 갱신해야 증강 선택 후 사라짐을 감지함.
                    # 하지만 "강제 리프레시" 중에는 화면이 안 바뀌었으므로, 
                    # 기존에 못 읽던 걸 갑자기 읽을 확률은 낮지만(Tesseract 노이즈), 
                    # 혹시나 초기 진입 실패를 복구할 수 있음.
                    self.cached_titles = titles 
                else:
                    titles = self.cached_titles

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