from flask import Flask, jsonify, request
from flask_cors import CORS
import time
import database
import lcu_driver
import win32gui
import threading
import json
import os
import sys

# 🔥 상점 감지기 & 증강 감지기 임포트
from augment_watcher import AugmentWatcher
import shop_detector 

app = Flask(__name__)
CORS(app)

# ==========================================
# 전역 상태 (Global State)
# ==========================================
STATE = {
    "active": False,        # 증강 오버레이 활성화 여부
    "champion": None,       # 현재 플레이어 챔피언
    "augments": [],         # 추천 증강 목록
    "ts": 0,                # 마지막 업데이트 시간
    "game_phase": "None",   # 게임 단계
    "shop_open": False      # 🔥 [추가] 상점 열림 상태 (백그라운드에서 업데이트)
}

# 빌드 데이터 저장소
BUILD_DATA = {}

# ==========================================
# 유틸리티 함수
# ==========================================
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def load_build_data():
    global BUILD_DATA
    try:
        path = resource_path(os.path.join("data", "aram_builds.json"))
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                BUILD_DATA = json.load(f)
            print(f"[Server] ✅ 빌드 데이터 로드 완료 ({len(BUILD_DATA)} champions)")
        else:
            print(f"[Server] ⚠️ 빌드 데이터 파일 없음: {path}")
    except Exception as e:
        print(f"[Server] ❌ 빌드 데이터 로드 실패: {e}")

def reset_state():
    print("[Server] 🔄 상태 초기화")
    STATE["active"] = False
    STATE["champion"] = None
    STATE["augments"] = []
    STATE["ts"] = 0
    STATE["shop_open"] = False # 상점 상태도 초기화

def get_lcu_window_rect():
    hwnd = win32gui.FindWindow(None, "League of Legends")
    if not hwnd: return None
    try:
        rect = win32gui.GetWindowRect(hwnd)
        x, y = rect[0], rect[1]
        w, h = rect[2] - x, rect[3] - y
        if w < 100 or h < 100: return None
        return {"x": x, "y": y, "w": w, "h": h}
    except: return None

# ==========================================
# 스레드 1: 게임 흐름 모니터링
# ==========================================
def monitor_gameflow():
    last_valid_phase = "None"
    print("[Server] GameFlow Monitor Started...")
    while True:
        try:
            try:
                current_phase = lcu_driver.driver.get("/lol-gameflow/v1/gameflow-phase")
            except: current_phase = "None"
            
            if not current_phase: current_phase = "None"
            STATE["game_phase"] = current_phase

            if current_phase == "None":
                time.sleep(1)
                continue

            if current_phase != last_valid_phase:
                print(f"[GameFlow] {last_valid_phase} -> {current_phase}")
                
                if current_phase == "ChampSelect":
                    reset_state()

                if current_phase == "EndOfGame" or (last_valid_phase == "InProgress" and current_phase == "Lobby"):
                    reset_state()
                        
                last_valid_phase = current_phase
                
            # 인게임 중 챔피언 정보 재확인 로직 (생략)
                
        except: pass
        time.sleep(1)

# ==========================================
# 스레드 2: 상점 감지 (백그라운드 실행) 🔥 [신규]
# ==========================================
def monitor_shop():
    print("[Server] Shop Monitor Started...")
    while True:
        try:
            # 게임 중이 아니면 굳이 상점 체크 안 함 (CPU 절약)
            if STATE.get("game_phase") != "InProgress":
                STATE["shop_open"] = False
                time.sleep(1)
                continue
            
            # 여기서 감지 수행 (약간의 시간이 걸려도 메인 스레드에 영향 없음)
            is_open = shop_detector.is_shop_open()
            STATE["shop_open"] = is_open
            
            # 0.5초마다 체크 (반응속도와 성능의 타협점)
            # shop_detector 내부에 이미 최적화(좌표 자르기 등)를 했다면 더 빨라짐
            time.sleep(0.5) 
            
        except Exception as e:
            print(f"[ShopMonitor] Error: {e}")
            time.sleep(1)

# ==========================================
# API 라우트
# ==========================================

@app.route("/champ-select")
def champ_select():
    current_phase = STATE.get("game_phase", "None")
    
    try:
        session = lcu_driver.driver.get("/lol-champ-select/v1/session")
        summoner = lcu_driver.driver.get("/lol-summoner/v1/current-summoner")
    except:
        session, summoner = None, None
        
    window_rect = get_lcu_window_rect()
    
    if not session or not summoner: 
        if current_phase == "ChampSelect":
             return jsonify({
                "phase": "ChampSelect", "team": [], "bench": [], "window_rect": window_rect
            })
        else:
            return jsonify({"phase": None, "window_rect": window_rect})

    cell_id = session.get("localPlayerCellId", -1)
    my_team = []
    
    for member in session.get("myTeam", []):
        c_id = member.get("championId", 0)
        name = lcu_driver.driver.get_champ_name(c_id)
        info = database.get_champion_info(name) if name else None
        
        if member["cellId"] == cell_id and name:
             STATE["champion"] = name 

        my_team.append({
            "name": name or "Unknown",
            "is_me": (member["cellId"] == cell_id),
            "tier": info["tier"] if info else "?",
            "score": info["score"] if info else None,
            "win_rate": info["win_rate"] if info else None,
        })

    bench = []
    for b in session.get("benchChampions", []):
        name = lcu_driver.driver.get_champ_name(b["championId"])
        if name:
            info = database.get_champion_info(name)
            bench.append({"name": name, **(info or {})})

    return jsonify({"phase": "ChampSelect", "team": my_team, "bench": bench, "window_rect": window_rect})

@app.route("/augments/current")
def augments_current():
    if time.time() - STATE["ts"] > 6.0: STATE["active"] = False
    return jsonify(STATE)

@app.route("/augments/update", methods=["POST"])
def augments_update():
    data = request.json or {}
    if not data.get("active"):
        STATE["active"] = False
        return jsonify({"ok": True})
        
    STATE["active"] = True
    STATE["ts"] = time.time()
    
    req_champ = data.get("champion")
    current_champ = req_champ if req_champ else STATE["champion"]
    
    enriched = database.enrich_ocr_augments(data.get("names_ko", []))
    champ_aug_map = {}
    
    if current_champ:
        rows = database.get_champion_augments(current_champ)
        for r in rows: champ_aug_map[r['name']] = r['tier'] 

    for item in enriched:
        t = champ_aug_map.get(item["name_en"])
        if not t: t = champ_aug_map.get(item["name_ko"])
        item["tier_champ"] = t
        
    STATE["augments"] = enriched
    return jsonify({"ok": True})

# 🔥 [최적화됨] 챔피언 빌드 정보
@app.route("/champion/build")
def get_champion_build():
    # ❌ [삭제] 여기서 직접 이미지 인식을 하지 않음 (렉 유발 원인 제거)
    # is_shop_open = shop_detector.is_shop_open()
    
    # ✅ [변경] 백그라운드 스레드가 업데이트해둔 값을 읽기만 함 (초고속)
    is_shop_open = STATE.get("shop_open", False)
    
    champ_name = STATE.get("champion")
    
    build_data = None
    if champ_name:
        build_data = BUILD_DATA.get(champ_name)
    
    return jsonify({
        "ok": True,
        "champion": champ_name,
        "shop_open": is_shop_open,
        "data": build_data
    })

def start_watcher():
    AugmentWatcher().start()

if __name__ == "__main__":
    load_build_data() 
    lcu_driver.driver.connect()
    
    # 스레드 시작
    threading.Thread(target=start_watcher, daemon=True).start()
    threading.Thread(target=monitor_gameflow, daemon=True).start()
    
    # 🔥 상점 감시 스레드 추가
    threading.Thread(target=monitor_shop, daemon=True).start()
    
    app.run(port=5000)