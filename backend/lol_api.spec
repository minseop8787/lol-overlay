# -*- mode: python ; coding: utf-8 -*-
# lol_api.spec - EasyOCR 버전 (PaddleOCR에서 전환)
# ============================================================
# 변경사항:
# 1. PaddleOCR → EasyOCR 전환
# 2. 의존성 대폭 단순화
# 3. Tesseract/PaddleX 완전 제거
# ============================================================

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# =========================
# EasyOCR Hidden Imports
# =========================
easyocr_hidden_imports = [
    # EasyOCR Core
    'easyocr',
    'easyocr.easyocr',
    
    # PyTorch (EasyOCR 의존성)
    'torch',
    'torchvision',
    
    # 이미지 처리 관련
    'PIL',
    'PIL.Image',
    'skimage',
    'skimage.transform',
    'cv2',
    
    # 기하학 연산
    'shapely',
    'shapely.geometry',
    'pyclipper',
    
    # 기타 의존성
    'yaml',
    'bidi',
    'bidi.algorithm',
]

# 동적 모듈 수집
jaraco_imports = collect_submodules('jaraco')
easyocr_submodules = collect_submodules('easyocr')

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        # ===== 필수 데이터 파일 =====
        ('augments_global_ko.json', '.'),
        ('augment_mapping_full.txt', '.'),
        ('game_data.db', '.'),
        ('assets', 'assets'),
        ('data', 'data'),
        
        # ===== EasyOCR 모델 (첫 실행 시 자동 다운로드됨) =====
        # 오프라인 배포가 필요하면 아래 주석 해제:
        # (os.path.expanduser('~/.EasyOCR/model'), 'easyocr_models'),
    ],
    hiddenimports=easyocr_hidden_imports + jaraco_imports + easyocr_submodules,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # ===== 용량 최적화: 불필요한 라이브러리 제외 =====
        'matplotlib',       # 시각화 불필요
        'tkinter',          # GUI 불필요
        'PyQt5',            # GUI 불필요
        'PyQt6',            # GUI 불필요
        'PySide2',          # GUI 불필요
        'PySide6',          # GUI 불필요
        'IPython',          # 인터랙티브 셸 불필요
        'notebook',         # Jupyter 불필요
        'sphinx',           # 문서 생성 불필요
        'pytest',           # 테스트 불필요
        
        # ===== 🔥 대용량 불필요 라이브러리 제거 (~350MB 절감) =====
        'tensorflow',       # 309MB - 완전 불필요
        'keras',            # TensorFlow 의존성
        'h5py',             # 6MB - TensorFlow 의존성
        'tensorboard',      # TensorFlow 의존성
        'pandas',           # 17MB - 불필요
        'grpc',             # 5MB - TensorFlow 의존성
        'google',           # TensorFlow 의존성
        
        # ===== 제거된 OCR 관련 =====
        'pytesseract',      # Tesseract 완전 제거
        'paddleocr',        # PaddleOCR 완전 제거
        'paddlex',          # PaddleX 완전 제거
        'paddle',           # PaddlePaddle 완전 제거
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='lol_api',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # 🔧 배포 시 False로 변경하면 콘솔 창 숨김
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='lol_api',
)