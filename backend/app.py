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
import io

# 🔥 [필수] 인코딩 설정 (PyInstaller 빌드 시 에러 방지)
sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.detach(), encoding='utf-8', errors='replace')

# 🔥 상점 감지기 & 증강 감지기 임포트
from augment_watcher import AugmentWatcher
import shop_detector 

app = Flask(__name__)
CORS(app)

# 🔥 [디버깅] 파일 로깅 추가 (빌드 후 실행 시 에러 확인용)
import logging
log_filename = os.path.join(os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__)), 'server_debug.txt')
logging.basicConfig(filename=log_filename, level=logging.DEBUG, 
                    format='%(asctime)s %(levelname)s: %(message)s', encoding='utf-8')

# 콘솔 출력도 로깅에 연결 (선택사항)
def log_print(*args, **kwargs):
    msg = " ".join(map(str, args))
    logging.info(msg)
    # print(msg, **kwargs) # 🔥 재귀 호출 방지: print 제거

# print 덮어쓰기 제거
# import builtins
# builtins.print = log_print

logging.info(f"[Server] Starting... Log file: {log_filename}")

# ==========================================
# 전역 상태 (Global State)
# ==========================================
STATE = {
    "active": False,        # 증강 오버레이 활성화 여부
    "champion": None,       # 현재 플레이어 챔피언 (이름)
    "augments": [],         # 추천 증강 목록
    "ts": 0,                # 마지막 업데이트 시간
    "game_phase": "None",   # 게임 단계
    "shop_open": False      # 상점 열림 상태
}

# 문자열 정규화 함수 (database.py의 함수 재사용)
normalize_name = database.normalize_name

# 빌드 데이터 저장소
BUILD_DATA = {}

# ==========================================
# 유틸리티 함수
# ==========================================
def resource_path(relative_path):
    """ PyInstaller 빌드 시 리소스 경로 찾기 """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# 전역 변수 하나 추가
BUILD_DATA_NORMALIZED = {} 

def load_build_data():
    global BUILD_DATA, BUILD_DATA_NORMALIZED
    try:
        path = resource_path(os.path.join("data", "aram_builds.json"))
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                BUILD_DATA = json.load(f)
                
            # 🔥 [수정] 검색을 위해 키를 정규화해서 따로 저장
            BUILD_DATA_NORMALIZED = {}
            for original_name, data in BUILD_DATA.items():
                clean_name = normalize_name(original_name)
                BUILD_DATA_NORMALIZED[clean_name] = data # 데이터는 그대로, 키만 변환
                
            print(f"[Server] ✅ 빌드 데이터 로드 완료 ({len(BUILD_DATA)} champions)")
        else:
            print(f"[Server] ⚠️ 빌드 데이터 파일 없음")
            BUILD_DATA = {}
            BUILD_DATA_NORMALIZED = {}
    except Exception as e:
        print(f"[Server] ❌ 빌드 데이터 로드 실패: {e}")

def reset_state():
    print("[Server] 🔄 상태 초기화")
    STATE["active"] = False
    STATE["champion"] = None
    STATE["augments"] = []
    STATE["ts"] = 0
    STATE["shop_open"] = False

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

# 🔥 [신규 함수] 게임 중일 때 내 챔피언 찾기 (중요!)
def fetch_current_champion():
    try:
        # 1. 내 소환사 정보 가져오기
        summoner = lcu_driver.driver.get("/lol-summoner/v1/current-summoner")
        my_summoner_id = summoner.get("summonerId")
        
        # 2. 게임 세션 정보 가져오기
        session = lcu_driver.driver.get("/lol-gameflow/v1/session")
        game_data = session.get("gameData", {})
        
        # 3. 팀 데이터에서 나(summonerId) 찾기
        all_players = game_data.get("teamOne", []) + game_data.get("teamTwo", [])
        
        for player in all_players:
            if player.get("summonerId") == my_summoner_id:
                champ_id = player.get("championId")
                champ_name = lcu_driver.driver.get_champ_name(champ_id)
                print(f"[Server] 🎮 게임 중 챔피언 재확인 완료: {champ_name}")
                return champ_name
    except Exception as e:
        print(f"[Server] 챔피언 재확인 실패: {e}")
    return None

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
            except: 
                current_phase = "None"
            
            # API가 실패하거나 None을 반환하면 "None" 문자열로 처리
            if not current_phase: current_phase = "None"
            STATE["game_phase"] = current_phase

            # LCU 연결 안됨 등
            if current_phase == "None":
                time.sleep(1)
                continue

            # 단계 변경 감지
            if current_phase != last_valid_phase:
                print(f"[GameFlow] {last_valid_phase} -> {current_phase}")
                
                # 챔피언 선택 시작 -> 초기화
                if current_phase == "ChampSelect":
                    reset_state()

                # 게임 종료 또는 로비로 이동 -> 초기화
                if current_phase == "EndOfGame" or (last_valid_phase == "InProgress" and current_phase == "Lobby"):
                    reset_state()
                        
                last_valid_phase = current_phase
            
            # 🔥 [추가 로직] 게임 중인데 챔피언 정보가 없으면 가져오기 (재접속/오버레이 재시작 대응)
            if current_phase == "InProgress" and STATE["champion"] is None:
                found_champ = fetch_current_champion()
                if found_champ:
                    STATE["champion"] = found_champ

        except Exception as e: 
            print(f"[GameFlow] Error: {e}")
            
        time.sleep(1)

import mss

# ==========================================
# 스레드 2: 상점 감지 (백그라운드 실행)
# ==========================================
def monitor_shop():
    print("[Server] 🛡️ 상점 감시 스레드 시작 (좀비 모드)")
    
    # 이전 상태를 기억해서, 상태가 바뀔 때만 로그를 찍음 (로그 폭주 방지)
    last_shop_state = False 
    
    # 🔥 MSS 인스턴스 생성 (재사용)
    sct = mss.mss()

    try:
        while True:
            try:
                # 1. 게임 중이 아니면 쉰다 (CPU 아끼기)
                if STATE.get("game_phase") != "InProgress":
                    # 게임이 끝났는데 상점이 열려있다고 되어있으면 닫음
                    if STATE["shop_open"]: 
                        STATE["shop_open"] = False
                        print("[ShopMonitor] 게임 종료로 인한 상태 초기화")
                    
                    time.sleep(2) # 푹 쉰다
                    continue
                
                # 2. 상점 감지 수행 (MSS 인스턴스 전달)
                is_open = shop_detector.is_shop_open(sct)
                
                # 3. 상태 업데이트
                STATE["shop_open"] = is_open
                
                # 🔥 [로그 최적화] 상태가 변했을 때만 로그 출력
                if is_open != last_shop_state:
                    status = "열림 🛒" if is_open else "닫힘 ❌"
                    print(f"[ShopMonitor] 상점 상태 변경: {status}")
                    last_shop_state = is_open
                    
                    # 상점이 닫힐 때 메모리 청소 한 번 해줌 (장시간 플레이 대비)
                    if not is_open:
                        import gc
                        gc.collect()

                # 0.5초 대기
                time.sleep(0.5) 
                
            except Exception as e:
                # 🔥 [핵심] 에러가 나도 절대 죽지 않고 로그만 남기고 다시 돔
                print(f"[ShopMonitor] ⚠️ 에러 발생 (스레드 생존): {e}")
                time.sleep(1) # 에러 났을 땐 1초 쉬었다가 다시 시도
    finally:
        sct.close()
# ==========================================
# API 라우트
# ==========================================

@app.route("/champ-select")
def champ_select():
    current_phase = STATE.get("game_phase", "None")
    window_rect = get_lcu_window_rect()
    
    # 챔피언 선택창이 아니면 빈 정보 반환
    if current_phase != "ChampSelect":
        return jsonify({"phase": current_phase, "window_rect": window_rect})

    try:
        session = lcu_driver.driver.get("/lol-champ-select/v1/session")
        summoner = lcu_driver.driver.get("/lol-summoner/v1/current-summoner")
    except:
        return jsonify({"phase": None, "window_rect": window_rect})
        
    if not session or not summoner: 
         return jsonify({"phase": "ChampSelect", "team": [], "bench": [], "window_rect": window_rect})

    cell_id = session.get("localPlayerCellId", -1)
    my_team = []
    
    # 우리 팀 정보 파싱
    for member in session.get("myTeam", []):
        c_id = member.get("championId", 0)
        name = lcu_driver.driver.get_champ_name(c_id)
        info = database.get_champion_info(name) if name else None
        
        # 내가 선택한 챔피언 저장
        if member["cellId"] == cell_id and name:
             STATE["champion"] = name 

        my_team.append({
            "name": name or "Unknown",
            "is_me": (member["cellId"] == cell_id),
            "tier": info["tier"] if info else "?",
            "score": info["score"] if info else None,
            "win_rate": info["win_rate"] if info else None,
        })

    # 벤치(주사위) 챔피언 파싱
    bench = []
    for b in session.get("benchChampions", []):
        name = lcu_driver.driver.get_champ_name(b["championId"])
        if name:
            info = database.get_champion_info(name)
            bench.append({"name": name, **(info or {})})

    return jsonify({"phase": "ChampSelect", "team": my_team, "bench": bench, "window_rect": window_rect})

@app.route("/augments/current")
def augments_current():
    # 마지막 업데이트가 6초 지났으면 증강 오버레이 끔
    if time.time() - STATE["ts"] > 6.0: STATE["active"] = False
    return jsonify(STATE)

@app.route("/augments/update", methods=["POST"])
def augments_update():
    data = request.json or {}
    
    # 증강 창이 닫혔다는 신호가 오면 끔
    if not data.get("active"):
        STATE["active"] = False
        return jsonify({"ok": True})
        
    STATE["active"] = True
    STATE["ts"] = time.time()
    
    # 요청에 챔피언 정보가 있으면 갱신 (보통 없음)
    req_champ = data.get("champion")
    current_champ = req_champ if req_champ else STATE["champion"]
    
    # 증강 티어 매핑
    enriched = database.enrich_ocr_augments(data.get("names_ko", []))
    champ_aug_map = {}
    
    if current_champ:
        rows = database.get_champion_augments(current_champ)
        for r in rows: 
            # 🔥 [수정 1] DB에서 가져온 이름도 정규화해서 키(Key)로 저장
            # 예: "Nunu & Willump" -> "nunuwillump" 로 저장됨
            clean_db_name = normalize_name(r['name'])
            champ_aug_map[clean_db_name] = r['tier'] 

    for item in enriched:
        # 🔥 [수정 2] OCR로 읽은 영어 이름을 정규화해서 찾기
        clean_en = normalize_name(item.get("name_en"))
        t = champ_aug_map.get(clean_en)
        
        # 🔥 [수정 3] 없으면 한글 이름도 정규화해서 다시 찾아보기 (안전장치)
        if not t:
            clean_ko = normalize_name(item.get("name_ko"))
            t = champ_aug_map.get(clean_ko)
            
        item["tier_champ"] = t
        
        # (디버깅용) 매핑 실패 시 로그 출력
        if not t and item.get("name_en"):
             print(f"⚠️ 증강 매핑 실패: {item.get('name_en')} (변환: {clean_en})")
        
    STATE["augments"] = enriched
    return jsonify({"ok": True})

# 챔피언 빌드 정보 (상점 열림 여부 포함)
@app.route("/champion/build")
def get_champion_build():
    is_shop_open = STATE.get("shop_open", False)
    champ_name = STATE.get("champion") # 예: "Kai'Sa"
    
    build_data = None
    if champ_name:
        # 🔥 [수정] 정규화된 이름으로 검색 (kaisa로 검색)
        clean_name = normalize_name(champ_name)
        build_data = BUILD_DATA_NORMALIZED.get(clean_name)
        
        # 만약 못 찾았으면 로그 찍어보기 (디버깅용)
        if not build_data:
            print(f"❌ 챔피언 매핑 실패: 원본[{champ_name}] -> 변환[{clean_name}]")
    
    return jsonify({
        "ok": True,
        "champion": champ_name,
        "shop_open": is_shop_open,
        "data": build_data
    })

import traceback

def start_watcher():
    retry_count = 0
    while retry_count < 5:
        try:
            print(f"[Server] AugmentWatcher Thread Starting (Attempt {retry_count+1})...")
            watcher = AugmentWatcher()
            watcher.start()
            print("[Server] AugmentWatcher Started Successfully.")
            return
        except Exception as e:
            print(f"[Server] ❌ AugmentWatcher Start Failed: {e}")
            traceback.print_exc()
            retry_count += 1
            time.sleep(2)
    print("[Server] ❌ AugmentWatcher failed to start after 5 attempts.")

if __name__ == "__main__":
    load_build_data() 
    lcu_driver.driver.connect()
    
    print("--- Starting Background Threads ---")
    
    # 스레드 시작
    threading.Thread(target=start_watcher, daemon=True).start()
    threading.Thread(target=monitor_gameflow, daemon=True).start()
    threading.Thread(target=monitor_shop, daemon=True).start()
    
    app.run(port=5000)