import time
import json
import os
import re
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

# ==========================================
# 1. 챔피언 이름 예외 처리 (Lolalytics URL 규칙)
# ==========================================
URL_EXCEPTIONS = {
    "Renata": "renata",
    "MonkeyKing": "wukong",
    "Nunu": "nunu",
    "DrMundo": "drmundo",
    "JarvanIV": "jarvaniv",
    "LeeSin": "leesin",
    "MasterYi": "masteryi",
    "MissFortune": "missfortune",
    "TahmKench": "tahmkench",
    "TwistedFate": "twistedfate",
    "XinZhao": "xinzhao",
    "KogMaw": "kogmaw",
    "RekSai": "reksai",
    "Belveth": "belveth",
    "Glasc": "renata" 
}

def get_champion_list():
    """라이엇 API에서 최신 챔피언 목록 가져오기"""
    try:
        ver_url = "https://ddragon.leagueoflegends.com/api/versions.json"
        version = requests.get(ver_url).json()[0]
        champ_url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/ko_KR/champion.json"
        data = requests.get(champ_url).json()
        return list(data['data'].keys())
    except Exception as e:
        print(f"⚠️ 챔피언 목록 가져오기 실패 (기본값 사용): {e}")
        return ["Gwen", "Ezreal", "Ahri"] 

def get_slug(champ_id):
    """챔피언 ID를 Lolalytics URL 슬러그로 변환"""
    if champ_id in URL_EXCEPTIONS: return URL_EXCEPTIONS[champ_id]
    return champ_id.lower().replace(" ", "").replace("'", "").replace(".", "")

def extract_id_from_url(url):
    """URL에서 아이템 ID 숫자만 추출 (예: .../1001.webp -> 1001)"""
    if not url: return None
    match = re.search(r'/(\d+)\.webp', url)
    return int(match.group(1)) if match else None

# ==========================================
# 2. 시작 아이템 파싱 함수 (수정됨)
# ==========================================
def parse_starting_items(driver):
    """
    [수정] 시작 아이템은 하나의 박스 안에 여러 아이템이 있고,
    승률/게임 수는 박스 맨 아래에 단 하나만 존재함.
    """
    items = []
    try:
        # 1. "Starting Items" 텍스트를 포함한 최상위 컨테이너 찾기
        xpath = "//div[contains(text(), 'Starting Items')]/ancestor::div[contains(@class, 'basis')]"
        containers = driver.find_elements(By.XPATH, xpath)

        for container in containers:
            # 2. 통계 정보 먼저 추출 (박스 하단에 있음)
            win_rate = ""
            games = ""
            try:
                wr_elem = container.find_element(By.CSS_SELECTOR, "span.text-green-500")
                win_rate = wr_elem.text.replace("%", "").replace(" Win Rate", "").strip()
            except: pass

            try:
                g_elem = container.find_element(By.CSS_SELECTOR, "span.text-gray-400")
                games = g_elem.text.replace(" Games", "").strip()
            except: pass

            # 3. 아이템 이미지들 추출
            # (중요: 툴팁용 작은 이미지가 아니라 메인 이미지를 찾아야 함. 보통 h-[34px] 안에 있음)
            imgs = container.find_elements(By.CSS_SELECTOR, "div.h-\\[34px\\] img")
            
            for img in imgs:
                src = img.get_attribute("src")
                item_id = extract_id_from_url(src)
                
                if item_id:
                    # 모든 아이템에 동일한 승률 적용
                    items.append({
                        "id": item_id,
                        "win": win_rate,
                        "games": games
                    })
    except Exception as e:
        pass # 섹션이 없을 수도 있음
        
    return items

# ==========================================
# 3. 일반 섹션 파싱 함수 (코어, 4, 5, 6 아이템)
# ==========================================
def parse_section(driver, header_text):
    """
    일반 섹션: 아이템별로 승률이 따로 붙어있는 경우 (Item 4, 5, 6 등)
    또는 코어 빌드처럼 순서대로 나열된 경우
    """
    items = []
    try:
        # 해당 헤더를 가진 컨테이너 찾기
        xpath = f"//div[contains(text(), '{header_text}')]/ancestor::div[contains(@class, 'basis')]"
        container = driver.find_element(By.XPATH, xpath)
        
        # 이미지와 통계가 묶여있는 블록들 찾기 (text-center 클래스 하위)
        # 보통 구조: div.text-center > div.overflow-hidden (이미지) + span (통계)
        blocks = container.find_elements(By.CSS_SELECTOR, "div.text-center")

        for block in blocks:
            try:
                # 이미지 찾기 (없으면 패스)
                try:
                    img = block.find_element(By.TAG_NAME, "img")
                except:
                    continue

                src = img.get_attribute("src")
                item_id = extract_id_from_url(src)
                if not item_id: continue

                # 통계 추출 (이미지와 형제 노드거나 부모의 형제일 수 있음)
                win_rate = ""
                games = ""
                
                # 블록 안에서 바로 찾기 시도
                try:
                    win_rate = block.find_element(By.CSS_SELECTOR, "span.text-green-500").text.replace("%", "").strip()
                except: pass
                
                try:
                    games = block.find_element(By.CSS_SELECTOR, "span.text-gray-400").text.replace(" Games", "").strip()
                except: pass

                # 유효한 아이템 데이터면 추가 (아이템 ID가 1000 이하면 보통 장식용일 수 있으므로 필터링 가능하지만 일단 수집)
                items.append({
                    "id": item_id,
                    "win": win_rate,
                    "games": games
                })
            except:
                continue
                
    except Exception as e:
        pass
        
    return items

def crawl_builds():
    # 브라우저 옵션 설정
    options = Options()
    # options.add_argument("--headless") # 디버깅 시에는 주석 처리 (브라우저 화면 보임)
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--log-level=3") # 불필요한 로그 숨김
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(options=options)
    champions = get_champion_list()
    all_data = {}

    print(f"🚀 총 {len(champions)}개 챔피언 크롤링 시작...")

    for i, champ in enumerate(champions):
        slug = get_slug(champ)
        url = f"https://lolalytics.com/lol/{slug}/aram/build/"
        print(f"[{i+1}/{len(champions)}] {champ} 수집 중... ({slug})")

        try:
            driver.get(url)
            # 페이지 로딩 대기 (네트워크 느리면 늘려주세요)
            time.sleep(2.5) 

            # 데이터 수집
            build_data = {
                "starting": parse_starting_items(driver),  # 시작 아이템 전용
                "core": parse_section(driver, "Core Build"),
                "item4": parse_section(driver, "Item 4"),
                "item5": parse_section(driver, "Item 5"),
                "item6": parse_section(driver, "Item 6"),
            }
            
            # 데이터가 유의미하면 저장
            if build_data["starting"] or build_data["core"]:
                all_data[champ] = build_data
                
        except Exception as e:
            print(f"❌ {champ} 수집 실패: {e}")

    driver.quit()

    # JSON 파일 저장
    # 저장 경로: backend/data/aram_builds.json
    save_dir = os.path.join("..", "backend", "data")
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, "aram_builds.json")
    
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)

    print(f"\n✅ 크롤링 완료! 저장된 파일: {os.path.abspath(save_path)}")

if __name__ == "__main__":
    crawl_builds()