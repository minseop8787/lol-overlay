"""
augment_watcher.py - 고성능 + 오류 보정 버전
===========================================
v2.0 업데이트:
1. Fuzzy Matching: OCR 오타 자동 보정 (cutoff=0.7)
2. Hash + Variance 이중 감지: 리롤 감지 강화
3. 강제 리프레시: 5초 이상 변화 없으면 OCR 재실행
4. 예외 처리 강화: 스레드 사망 방지
"""
import time
import threading
import re
import os
import sys
import gc
import difflib
from pathlib import Path

import numpy as np
import cv2
import mss
import requests

# =========================
# PaddleOCR 초기화
# =========================
from paddleocr import TextRecognition

print("[Watcher] Loading PaddleOCR Model (korean_PP-OCRv5_mobile_rec)...")
OCR_MODEL = TextRecognition(model_name="korean_PP-OCRv5_mobile_rec")
print("[Watcher] ✅ PaddleOCR Model Loaded!")

# =========================
# 설정값
# =========================
def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

MAPPING_TXT_PATH = Path(resource_path("augment_mapping_full.txt"))
POLL_INTERVAL = 0.2
GC_INTERVAL = 600
FORCE_REFRESH_INTERVAL = 5.0  # [신규] 5초마다 강제 OCR 재실행
FUZZY_CUTOFF = 0.7            # [신규] 퍼지 매칭 최소 유사도

# =========================
# 해상도별 ROI 좌표
# =========================
RESOLUTION_MAP = {
    1920: [
        {"left": 474, "top": 412, "width": 266, "height": 35},
        {"left": 820, "top": 412, "width": 273, "height": 35},
        {"left": 1180, "top": 412, "width": 267, "height": 35}
    ],
    2560: [
        {"left": 789, "top": 410, "width": 274, "height": 38},
        {"left": 1143, "top": 414, "width": 270, "height": 32},
        {"left": 1500, "top": 413, "width": 267, "height": 34}
    ]
}

# =========================
# [개선 1] Fuzzy Matching 시스템
# =========================
VALID_NAMES_SET = set()
VALID_NAMES_LIST = []  # difflib용 리스트
VALID_NAMES_NORMALIZED = {}

def normalize_text(text):
    if not text:
        return ""
    return re.sub(r'[^\w가-힣]', '', text).strip().lower()

def load_valid_names():
    global VALID_NAMES_SET, VALID_NAMES_LIST, VALID_NAMES_NORMALIZED
    if not os.path.exists(MAPPING_TXT_PATH):
        print(f"[Watcher] ⚠️ Mapping file not found: {MAPPING_TXT_PATH}")
        return
    try:
        with open(MAPPING_TXT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if " : " in line:
                    ko, _ = line.split(" : ", 1)
                    original = ko.strip()
                    normalized = normalize_text(original)
                    VALID_NAMES_SET.add(normalized)
                    VALID_NAMES_NORMALIZED[normalized] = original
        VALID_NAMES_LIST = list(VALID_NAMES_SET)
        print(f"[Watcher] Loaded {len(VALID_NAMES_SET)} valid augment names (Fuzzy Ready).")
    except Exception as e:
        print(f"[Watcher] Error loading mapping file: {e}")

def find_closest_match(text):
    """
    [개선 1] OCR 결과를 가장 유사한 증강 이름으로 보정
    - 정확히 일치하면 그대로 반환
    - 아니면 difflib으로 가장 유사한 것 찾기
    - "핵심분요술사" → "핵심룬요술사"
    """
    normalized = normalize_text(text)
    
    # 1. 정확히 일치
    if normalized in VALID_NAMES_SET:
        return normalized
    
    # 2. Fuzzy Matching
    if not VALID_NAMES_LIST:
        return None
    
    matches = difflib.get_close_matches(normalized, VALID_NAMES_LIST, n=1, cutoff=FUZZY_CUTOFF)
    if matches:
        corrected = matches[0]
        if corrected != normalized:
            print(f"[Watcher] 🔧 OCR 보정: '{normalized}' → '{corrected}'")
        return corrected
    
    return None

def is_valid_text(text):
    """퍼지 매칭으로 유효성 검사"""
    return find_closest_match(text) is not None

# =========================
# ROI Capture
# =========================
def get_roi_configs(screen_width):
    if screen_width >= 2500:
        return RESOLUTION_MAP[2560]
    return RESOLUTION_MAP[1920]

def capture_rois(sct, roi_configs):
    roi_images = []
    for roi in roi_configs:
        try:
            img = np.array(sct.grab(roi))
            bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            roi_images.append(bgr)
        except Exception:
            roi_images.append(None)
    return roi_images

# =========================
# [개선 2] Hash + Variance 이중 감지
# =========================
def compute_roi_hash(roi_images):
    if not roi_images or any(img is None for img in roi_images):
        return None
    
    hash_values = []
    for img in roi_images:
        small = cv2.resize(img, (8, 8), interpolation=cv2.INTER_NEAREST)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        hash_values.append(gray.tobytes())
    
    return b''.join(hash_values)

def compute_variance(roi_images):
    """
    [개선 2] 이미지 분산값 계산
    리롤 애니메이션 중 색상이 변하면 분산도 변함
    """
    if not roi_images or any(img is None for img in roi_images):
        return 0
    
    total_var = 0
    for img in roi_images:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        total_var += np.var(gray)
    return total_var

def is_roi_changed(old_hash, new_hash, old_var, new_var, var_threshold=500):
    """
    [개선 2] 해시 또는 분산이 변했으면 True
    """
    # 둘 중 하나라도 None이면 변화로 간주
    if old_hash is None or new_hash is None:
        return True
    
    # 해시가 다르면 확실히 변화
    if old_hash != new_hash:
        return True
    
    # 해시가 같더라도 분산 차이가 크면 변화 (리롤 애니메이션 감지)
    if abs(old_var - new_var) > var_threshold:
        return True
    
    return False

# =========================
# OCR 처리 (Fuzzy Matching 적용)
# =========================
def extract_titles_batch(roi_images):
    if not roi_images or any(img is None for img in roi_images):
        return []
    
    raw_titles = []
    
    try:
        for roi in roi_images:
            output = OCR_MODEL.predict(input=roi, batch_size=1)
            for res in output:
                text = res.get("rec_text", "") if hasattr(res, 'get') else ""
                if not text and hasattr(res, 'rec_text'):
                    text = res.rec_text
                if text:
                    raw_titles.append(text)
                break
    except Exception as e:
        print(f"[Watcher] PaddleOCR Error: {e}")
        return []
    
    if len(raw_titles) != 3:
        return []
    
    # [개선 1] Fuzzy Matching으로 보정
    corrected_titles = []
    for raw in raw_titles:
        corrected = find_closest_match(raw)
        if corrected:
            corrected_titles.append(corrected)
    
    # 3개 모두 유효해야 함 (보정 후 기준)
    if len(corrected_titles) != 3:
        return []
    
    return corrected_titles

# =========================
# Watcher Class
# =========================
class AugmentWatcher:
    def __init__(self):
        self._stop_event = threading.Event()
        self._thread = None
        
        # 해시 및 분산 기반 감지
        self.last_roi_hash = None
        self.last_roi_var = 0
        
        # 상태 관리
        self.last_candidates = []
        self.stability_count = 0
        self.required_stability = 2
        self.last_sent_titles = []
        self.last_sent_time = 0
        self.cached_titles = []
        
        # 타이머
        self.last_gc_time = time.time()
        self.last_ocr_time = time.time()  # [개선 3] 강제 리프레시용

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
        print("[Watcher] OCR Monitoring started (PaddleOCR, v2.0)...")
        error_count = 0
        
        with mss.mss() as sct:
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            screen_width = monitor["width"]
            roi_configs = get_roi_configs(screen_width)
            print(f"[Watcher] Screen: {screen_width}px, ROI: {len(roi_configs)}")
            
            while not self._stop_event.is_set():
                try:
                    time.sleep(POLL_INTERVAL)
                    current_time = time.time()
                    
                    # 주기적 GC
                    if current_time - self.last_gc_time > GC_INTERVAL:
                        gc.collect()
                        self.last_gc_time = current_time
                    
                    # ROI 캡처
                    roi_images = capture_rois(sct, roi_configs)
                    if any(img is None for img in roi_images):
                        time.sleep(1)
                        continue
                    
                    # [개선 2] 해시 + 분산 계산
                    current_hash = compute_roi_hash(roi_images)
                    current_var = compute_variance(roi_images)
                    
                    # [개선 2] 이중 감지
                    has_changed = is_roi_changed(
                        self.last_roi_hash, current_hash,
                        self.last_roi_var, current_var
                    )
                    
                    # [개선 3] 강제 리프레시 (5초 이상 OCR 안 했으면)
                    force_refresh = (current_time - self.last_ocr_time > FORCE_REFRESH_INTERVAL)
                    
                    self.last_roi_hash = current_hash
                    self.last_roi_var = current_var
                    
                    # OCR 실행 조건: 변화 감지 OR 강제 리프레시
                    if has_changed or force_refresh:
                        titles = extract_titles_batch(roi_images)
                        self.cached_titles = titles
                        self.last_ocr_time = current_time
                        
                        if force_refresh and not has_changed and titles:
                            print("[Watcher] ⏰ Force refresh executed")
                    else:
                        titles = self.cached_titles
                    
                    # 메모리 해제
                    del roi_images
                    
                    # 결과 처리
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
                        if (titles != self.last_sent_titles) or (current_time - self.last_sent_time > 3.0):
                            print(f"[Watcher] Detected: {titles}")
                            self._send_titles(titles)
                            self.last_sent_titles = titles
                            self.last_sent_time = current_time
                            self._smart_sleep(2.0, sct, roi_configs)
                            error_count = 0

                except Exception as e:
                    # [개선 4] 예외 처리 강화 - 절대 죽지 않음
                    error_count += 1
                    if error_count % 10 == 0:
                        print(f"[Watcher] Loop Error #{error_count}: {e}")
                    time.sleep(1)

    def _smart_sleep(self, duration, sct, roi_configs):
        """[개선 4] 타임아웃 기반 안전한 대기"""
        deadline = time.time() + duration
        
        while time.time() < deadline:
            if self._stop_event.is_set():
                break
            
            time.sleep(0.2)
            
            try:
                roi_images = capture_rois(sct, roi_configs)
                current_hash = compute_roi_hash(roi_images)
                current_var = compute_variance(roi_images)
                del roi_images
                
                if is_roi_changed(self.last_roi_hash, current_hash, 
                                 self.last_roi_var, current_var):
                    print("[Watcher] 🔄 Reroll detected! Waking up...")
                    break
            except Exception:
                # 예외 발생 시 즉시 탈출
                break

    def _send_titles(self, titles):
        try:
            requests.post("http://127.0.0.1:5000/augments/update", json={
                "active": True, "names_ko": titles, "champion": ""
            }, timeout=1)
        except:
            pass

    def _send_inactive(self):
        if not self.last_sent_titles:
            return
        try:
            requests.post("http://127.0.0.1:5000/augments/update", 
                         json={"active": False}, timeout=1)
            self.last_sent_titles = []
        except:
            pass

if __name__ == "__main__":
    watcher = AugmentWatcher()
    watcher.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        watcher.stop()