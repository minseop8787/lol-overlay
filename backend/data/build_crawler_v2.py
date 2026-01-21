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
    "Glasc": "renata" # 혹시 몰라 추가
}

def get_champion_list():
    """라이엇 API에서 최신 챔피언 목록 가져오기"""
    try:
        ver_url = "https://ddragon.leagueoflegends.com/api/versions.json"
        version = requests.get(ver_url).json()[0]
        champ_url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/ko_KR/champion.json"
        data = requests.get(champ_url).json()
        return list(data['data'].keys())
    except:
        return ["Gwen", "Ezreal", "Ahri"] # 실패 시 테스트용 더미

def get_slug(champ_id):
    if champ_id in URL_EXCEPTIONS: return URL_EXCEPTIONS[champ_id]
    return champ_id.lower().replace(" ", "").replace("'", "").replace(".", "")

def extract_id_from_url(url):
    """URL에서 아이템 ID 숫자만 추출 (예: .../1001.webp -> 1001)"""
    if not url: return None
    match = re.search(r'/(\d+)\.webp', url)
    return int(match.group(1)) if match else None

def parse_section(driver, header_text):
    """특정 헤더(예: Starting Items) 아래의 아이템과 통계를 추출"""
    items = []
    try:
        # 1. 헤더 텍스트로 해당 섹션(컨테이너) 찾기 (XPath 사용)
        # "Starting Items"라는 텍스트를 가진 div의 상위 부모들 중 적절한 컨테이너를 찾음
        xpath = f"//div[contains(text(), '{header_text}')]/ancestor::div[contains(@class, 'basis')]"
        container = driver.find_element(By.XPATH, xpath)
        
        # 2. 해당 컨테이너 안의 모든 아이템 블록(이미지가 있는 div) 찾기
        # text-center 클래스를 가진 div 안에 이미지가 있음
        item_blocks = container.find_elements(By.CSS_SELECTOR, "div.text-center > div.overflow-hidden")

        for block in item_blocks:
            try:
                # 이미지 추출
                img = block.find_element(By.TAG_NAME, "img")
                src = img.get_attribute("src")
                item_id = extract_id_from_url(src)
                if not item_id: continue

                # 통계 추출 (이미지 블록의 부모의 형제나 자식에서 찾기)
                # 구조상 이미지 바로 아래나 옆에 통계 div가 있음
                # 상위 부모(text-center)로 올라가서 통계 찾기
                parent = block.find_element(By.XPATH, "..") 
                
                win_rate = ""
                games = ""
                
                try:
                    # 승률 (초록색 텍스트)
                    wr_elem = parent.find_element(By.CSS_SELECTOR, "span.text-green-500")
                    win_rate = wr_elem.text.replace("%", "").replace(" Win Rate", "").strip()
                except: pass

                try:
                    # 게임 수 (회색 텍스트)
                    g_elem = parent.find_element(By.CSS_SELECTOR, "span.text-gray-400")
                    games = g_elem.text.replace(" Games", "").strip()
                except: pass

                items.append({
                    "id": item_id,
                    "win": win_rate,
                    "games": games
                })
            except:
                continue
                
    except Exception as e:
        # 해당 섹션이 없을 수도 있음 (무시)
        pass
        
    return items

def crawl_builds():
    options = Options()
    # options.add_argument("--headless") # 디버깅할 땐 주석 처리해서 브라우저 뜨는 거 보세요
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(options=options)
    champions = get_champion_list()
    all_data = {}

    print(f"🚀 {len(champions)}개 챔피언 크롤링 시작...")

    for i, champ in enumerate(champions):
        slug = get_slug(champ)
        url = f"https://lolalytics.com/lol/{slug}/aram/build/"
        print(f"[{i+1}/{len(champions)}] {champ} -> {url}")

        try:
            driver.get(url)
            time.sleep(3) # 페이지 로딩 대기

            build_data = {
                "starting": parse_section(driver, "Starting Items"),
                "core": parse_section(driver, "Core Build"),
                "item4": parse_section(driver, "Item 4"),
                "item5": parse_section(driver, "Item 5"),
                "item6": parse_section(driver, "Item 6"),
            }
            
            # 데이터가 비어있으면 저장 안 함
            if build_data["starting"] or build_data["core"]:
                all_data[champ] = build_data
                
        except Exception as e:
            print(f"❌ Error {champ}: {e}")

    driver.quit()

    # JSON 저장
    save_path = os.path.join("..", "backend", "data", "aram_builds.json")
    os.makedirs(os.path.dirname(save_path), exist_ok=True) # 폴더 없으면 생성
    
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)

    print(f"✅ 저장 완료: {save_path}")

if __name__ == "__main__":
    crawl_builds()