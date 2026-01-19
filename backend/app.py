from flask import Flask, jsonify, request
from flask_cors import CORS
import time
import database
import lcu_driver
import win32gui
import threading
from augment_watcher import AugmentWatcher

app = Flask(__name__)
CORS(app)

# =========================
# 상태 저장소 (State)
# =========================
STATE = {
    "active": False,
    "champion": None,     # 현재 내가 픽한 챔피언
    "augments": [],
    "ts": 0,              # 마지막 업데이트 시간
    "game_phase": "None"  # 게임 진행 상태 (Lobby, ChampSelect, InProgress...)
}

def reset_state():
    """게임을 마쳤을 때 상태를 깨끗하게 초기화하는 함수"""
    print("[Server] 🔄 게임 종료 감지 -> 상태 초기화")
    STATE["active"] = False
    STATE["champion"] = None
    STATE["augments"] = []
    STATE["ts"] = 0
    # game_phase는 모니터링 중이므로 건드리지 않음

# =========================
# LCU 윈도우 좌표 찾기
# =========================
def get_lcu_window_rect():
    hwnd = win32gui.FindWindow(None, "League of Legends")
    if not hwnd:
        return None
    try:
        rect = win32gui.GetWindowRect(hwnd)
        x, y = rect[0], rect[1]
        w, h = rect[2] - x, rect[3] - y
        if w < 100 or h < 100: return None
        return {"x": x, "y": y, "w": w, "h": h}
    except:
        return None

# =========================
# 게임 흐름 감시 (수정됨: None 상태 무시 및 강제 리셋 강화)
# =========================
def monitor_gameflow():
    """롤 클라이언트의 상태를 감시하여 게임 종료 시 리셋"""
    last_valid_phase = "None" # 'None'이 아닌 마지막 유효 상태를 기억
    
    print("[Server] GameFlow Monitor Started (Robust Mode)...")
    
    while True:
        try:
            # 1. 롤 클라이언트 상태 조회
            try:
                current_phase = lcu_driver.driver.get("/lol-gameflow/v1/gameflow-phase")
            except:
                current_phase = "None"
            
            # API가 가끔 None을 뱉거나 연결이 끊기면 "None" 문자열로 처리
            if not current_phase:
                current_phase = "None"

            # 2. 상태 저장 (None이라도 일단 저장은 함)
            STATE["game_phase"] = current_phase

            # 3. 상태 변화 감지 로직
            # 중요: 현재 상태가 'None'이면 로직 판단을 건너뛰고, 이전 상태(last_valid_phase)를 유지함
            if current_phase == "None":
                time.sleep(1)
                continue

            if current_phase != last_valid_phase:
                print(f"[GameFlow] 상태 변경: {last_valid_phase} -> {current_phase}")
                
                # ✅ [핵심 수정 1] 픽창(ChampSelect) 진입 시 무조건 초기화
                # 이전 판 데이터가 남아있을 수 있으므로, 픽창 들어오면 일단 싹 비우고 시작
                if current_phase == "ChampSelect":
                    print("[GameFlow] 픽창 진입! 강제 상태 초기화 실행.")
                    reset_state() # 여기서 확실하게 비워줌!

                # ✅ [핵심 수정 2] 게임 종료 감지 (InProgress -> Lobby)
                # 중간에 None이 끼어도 last_valid_phase는 InProgress였으므로 정상 작동함
                if current_phase == "EndOfGame" or (last_valid_phase == "InProgress" and current_phase == "Lobby"):
                    print("[GameFlow] 게임 종료 확인. 리셋.")
                    reset_state()

                # 유효한 상태만 업데이트
                last_valid_phase = current_phase
            
        except Exception as e:
            print(f"[GameFlow Error] {e}")
        
        time.sleep(1) # 1초마다 체크

# =========================
# API 라우트
# =========================

@app.route("/champ-select")
def champ_select():
    # 연결 안됐으면 빈값 리턴
    try:
        session = lcu_driver.driver.get("/lol-champ-select/v1/session")
        summoner = lcu_driver.driver.get("/lol-summoner/v1/current-summoner")
    except:
        return jsonify({"phase": None, "window_rect": None})
        
    window_rect = get_lcu_window_rect()
    
    if not session or not summoner: 
        return jsonify({"phase": None, "window_rect": window_rect})

    cell_id = session.get("localPlayerCellId", -1)
    
    my_team = []
    my_team_raw = session.get("myTeam", [])
    
    for member in my_team_raw:
        c_id = member.get("championId", 0)
        name = lcu_driver.driver.get_champ_name(c_id)
        
        info = None
        if name:
            info = database.get_champion_info(name)
        
        # 내가 픽한 챔피언이면 전역 변수에 저장 (중요)
        if member["cellId"] == cell_id and name:
             # 챔피언이 바뀌었으면 로그 출력
             if STATE["champion"] != name:
                 print(f"[Server] 내 챔피언 감지됨: {name}")
             STATE["champion"] = name 

        my_team.append({
            "name": name or "Unknown",
            "is_me": (member["cellId"] == cell_id),
            "tier": info["tier"] if info else "?",
            "score": info["score"] if info else None,
            "win_rate": info["win_rate"] if info else None,
            "pick_rate": info.get("pick_rate") if info else None
        })

    bench = []
    for b in session.get("benchChampions", []):
        name = lcu_driver.driver.get_champ_name(b["championId"])
        if name:
            info = database.get_champion_info(name)
            bench.append({"name": name, **(info or {"tier": "?", "score": None})})

    return jsonify({
        "phase": "ChampSelect", 
        "team": my_team,
        "bench": bench,
        "window_rect": window_rect
    })

@app.route("/augments/current")
def augments_current():
    # 6초 동안 업데이트 없으면 오버레이 끄기 (타임아웃)
    if time.time() - STATE["ts"] > 6.0:
        STATE["active"] = False
    return jsonify(STATE)

@app.route("/augments/update", methods=["POST"])
def augments_update():
    data = request.json or {}
    
    # 워쳐가 "꺼라"고 신호 보낸 경우
    if not data.get("active"):
        STATE["active"] = False
        return jsonify({"ok": True})
        
    STATE["active"] = True
    STATE["ts"] = time.time()
    
    # 요청에 챔피언 정보가 있으면 쓰고, 없으면 픽창에서 저장한거 씀
    req_champ = data.get("champion")
    if req_champ:
        current_champ = req_champ
    else:
        current_champ = STATE["champion"]
    
    # DB 조회 및 데이터 가공
    enriched = database.enrich_ocr_augments(data.get("names_ko", []))
    
    champ_aug_map = {}
    if current_champ:
        rows = database.get_champion_augments(current_champ)
        for r in rows:
            champ_aug_map[r['name']] = r['tier'] 

    for item in enriched:
        t = champ_aug_map.get(item["name_en"])
        if not t: t = champ_aug_map.get(item["name_ko"])
        item["tier_champ"] = t
        
    STATE["augments"] = enriched
    return jsonify({"ok": True})

# =========================
# 메인 실행부
# =========================
def start_watcher():
    watcher = AugmentWatcher()
    watcher.start()

if __name__ == "__main__":
    print("[Server] Starting LoL Overlay Backend...")
    
    # 1. LCU 연결
    lcu_driver.driver.connect()
    
    # 2. OCR 워쳐 스레드 시작
    watcher_thread = threading.Thread(target=start_watcher, daemon=True)
    watcher_thread.start()

    # 3. 🔥 게임 흐름 감시 스레드 시작 (새로 추가됨)
    gameflow_thread = threading.Thread(target=monitor_gameflow, daemon=True)
    gameflow_thread.start()

    # 4. 플라스크 서버 시작
    app.run(port=5000)