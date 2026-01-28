# 롤 칼바람나락 증강 오버레이 (LoL ARAM Augment Overlay)

리그 오브 레전드 무작위 총력전(ARAM) 모드에서 증강 선택지를 **Pixel-Perfect OCR**로 인식하고, 화면에 티어 정보와 팁을 바로 띄워주는 지능형 오버레이 프로그램입니다.

## 🚀 주요 기능 (v1.0.8 최신 기술)

### 1. 🔍 하이브리드 인식 엔진 (Hybrid Perception Engine)
기존 시스템들의 단점을 모두 보완한 **3단계 검증 시스템**을 탑재했습니다.
1.  **UI 템플릿 매칭 (Gatekeeper)**: 화면에 "증강 선택 버튼(Confirm Button)"이 정확히(85% 일치) 존재하는지 먼저 확인합니다. 일반 게임 상황에서의 **오작동(False Positive)을 100% 차단**합니다.
2.  **Tesseract OCR 5.0 (Reader)**: 버튼이 확인되면, 3개의 카드 영역만 정밀 스캔하여 텍스트를 추출합니다.
3.  **퍼지 텍스트 매칭 (Validator)**: 인식된 글자에 오타가 있더라도, 자체 보유한 155개 증강 데이터베이스와 대조하여 올바른 이름을 찾아냅니다. (예: "마범공학" -> "마법공학")



### 2. 🛡️ 안티 고스팅 (Ghost Overlay Prevention)
*   **데이터 필터링 예외 처리**: DB에 없는 신규/희귀 증강이 나오더라도 오버레이가 사라지지 않고 "이름"은 표시해주도록 로직을 개선했습니다 (`Unknown` 태그 처리).
*   **프로세스 강제 정리**: 설치 및 종료 시 좀비 프로세스(`taskkill`)를 자동으로 정리하여 충돌을 방지합니다.

---

## 🛠️ 기술 아키텍처

*   **Backend (`/backend`)**:
    *   **Core**: Python 3.10, Flask (API Server).
    *   **Vision**: OpenCV (템플릿 매칭), Tesseract-OCR (텍스트 인식), MSS (초고속 화면 캡처).
    *   **Data**: SQLite (게임 데이터), JSON (설정 및 매핑).
    *   **Packaging**: PyInstaller (Tesseract 엔진 및 에셋 번들링, 시스템 DLL 포함).

*   **Frontend (`/frontend`)**:
    *   **Core**: React 18 (UI).
    *   **Engine**: Electron 28 (투명 윈도우, 프로세스 관리).
    *   **UX**: 마우스 이벤트 투과(Click-through) 및 툴팁 인터랙션 동시 지원.

---

## 📦 빌드 및 실행 가이드

### 필수 요구사항
*   **Node.js**: v16+
*   **Python**: v3.10+ (Anaconda 권장)
*   **Tesseract-OCR**: `backend/Tesseract-OCR` 폴더에 바이너리 포함 필요.

### v1.0.8 (Current)
*   **[개선] 오인식 방지 로직**: 증강 선택 버튼(Confirm Button) 템플릿 매칭 추가 (신뢰도 0.85).
*   **[복구] OCR 엔진 재도입**: 유사 이미지 구분을 위해 이미지 매칭 -> OCR로 회귀 (정확도 상승).
*   **[수정] 빈 화면 버그**: DB 매핑 실패 시에도 원본 텍스트를 출력하도록 Fallback 로직 추가.
*   **[수정] 설치 오류**: `taskkill` 명령어로 잔존 프로세스 자동 종료 기능 추가.
