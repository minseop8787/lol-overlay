import base64
import requests
import psutil
from urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

class LcuDriver:
    def __init__(self):
        self.port = None
        self.auth_token = None
        self.headers = {}
        self.base_url = ""
        self.connected = False
        self.id_to_name = {}

    def connect(self):
        try:
            # 1. DDragon 데이터 로드 (ID -> Name)
            ver = requests.get("https://ddragon.leagueoflegends.com/api/versions.json").json()[0]
            data = requests.get(f"https://ddragon.leagueoflegends.com/cdn/{ver}/data/en_US/champion.json").json()["data"]
            self.id_to_name = {}
            name_fixes = {
                "Nunu & Willump": "Nunu",
                "Kha'Zix": "Khazix",
                "Kai'Sa": "Kaisa",
                "Vel'Koz": "Velkoz",
                "Cho'Gath": "Chogath",
                "Bel'Veth": "Belveth",
                "Kog'Maw": "KogMaw",
                "Rek'Sai": "Reksai",
                "Dr. Mundo": "DrMundo",
                "Renata Glasc": "Renata",
                "Wukong": "MonkeyKing", # 가끔 Wukong 대신 MonkeyKing을 쓰는 데이터가 있음
                "LeBlanc": "Leblanc"
            }
            for v in data.values():
                c_id = int(v["key"])
                c_name = v["name"]
                
                # 🛠️ 누누 강제 개명 (Nunu & Willump -> Nunu)
                if c_name in name_fixes:
                    c_name = name_fixes[c_name]
                self.id_to_name[c_id] = c_name

            # 2. LCU 프로세스 연결
            for proc in psutil.process_iter(['name', 'cmdline']):
                if proc.info['name'] == 'LeagueClientUx.exe':
                    for arg in proc.info['cmdline']:
                        if arg.startswith('--app-port='): self.port = arg.split('=')[1]
                        if arg.startswith('--remoting-auth-token='): self.auth_token = base64.b64encode(f"riot:{arg.split('=')[1]}".encode()).decode()
                    self.headers = {"Authorization": f"Basic {self.auth_token}", "Accept": "application/json"}
                    self.base_url = f"https://127.0.0.1:{self.port}"
                    self.connected = True
                    return True
        except: pass
        return False

    def get(self, endpoint):
        if not self.connected and not self.connect(): return None
        try:
            return requests.get(f"{self.base_url}{endpoint}", headers=self.headers, verify=False, timeout=1).json()
        except:
            self.connected = False
            return None

    def get_champ_name(self, champ_id):
        return self.id_to_name.get(int(champ_id))

driver = LcuDriver()