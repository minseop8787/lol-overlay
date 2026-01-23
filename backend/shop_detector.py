import cv2
import numpy as np
import mss
import os
import sys

# PyInstaller 경로 대응 함수
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

# 템플릿 로드 (경로 수정)
TEMPLATE_PATH = resource_path(os.path.join("assets", "shop_template.png"))

template = None
if os.path.exists(TEMPLATE_PATH):
    # 이미지를 흑백으로 읽으면 속도가 더 빠르고 조명 영향을 덜 받습니다.
    # 하지만 색상 정보가 중요하다면 IMREAD_COLOR 유지하세요. 여기선 그대로 둡니다.
    template = cv2.imread(TEMPLATE_PATH, cv2.IMREAD_COLOR)
else:
    print(f"[Warning] 상점 템플릿 없음: {TEMPLATE_PATH}")

def is_shop_open(sct=None):
    if template is None: return False

    if sct:
        # 이미터 인스턴스 사용
        monitor = sct.monitors[1]
        screen_shot = np.array(sct.grab(monitor))
        screen_bgr = cv2.cvtColor(screen_shot, cv2.COLOR_BGRA2BGR)
        return _check_template(screen_bgr)
    else:
        # 기존 방식 (매번 생성)
        with mss.mss() as sct_new:
            monitor = sct_new.monitors[1]
            screen_shot = np.array(sct_new.grab(monitor))
            screen_bgr = cv2.cvtColor(screen_shot, cv2.COLOR_BGRA2BGR)
            return _check_template(screen_bgr)

def _check_template(screen_bgr):
    # 템플릿 매칭
    res = cv2.matchTemplate(screen_bgr, template, cv2.TM_CCOEFF_NORMED)

    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
    # print(f"[ShopDetector] 일치율: {max_val:.2f}") 
    
    # 🔥 [수정] 이미지가 선명하므로 기준을 0.9로 상향 조정 (오인식 차단)
    threshold = 0.9
    
    loc = np.where(res >= threshold)
    if len(loc[0]) > 0:
        return True
    return False