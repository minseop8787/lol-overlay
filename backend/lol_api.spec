# -*- mode: python ; coding: utf-8 -*-
# lol_api.spec - RapidOCR 버전 (ONNX Runtime 기반)
# ============================================================
# 변경사항:
# 1. PaddleOCR/PaddleX → RapidOCR 전환
# 2. ONNX Runtime 기반으로 의존성 대폭 단순화
# 3. PyTorch/PaddlePaddle 완전 제거
# ============================================================

# 🔥 [중요] RecursionError 해결을 위한 재귀 한도 증가
import sys
sys.setrecursionlimit(sys.getrecursionlimit() * 5)

from PyInstaller.utils.hooks import collect_submodules, collect_data_files
import os

block_cipher = None

# =========================
# RapidOCR Hidden Imports
# =========================
rapidocr_hidden_imports = [
    # RapidOCR Core
    'rapidocr_onnxruntime',
    
    # ONNX Runtime
    'onnxruntime',
    
    # 이미지 처리 관련
    'PIL',
    'PIL.Image',
    'cv2',
    
    # 기하학 연산
    'shapely',
    'shapely.geometry',
    'pyclipper',
    
    # 기타 의존성
    'yaml',
]

# 동적 모듈 수집
jaraco_imports = collect_submodules('jaraco')
rapidocr_submodules = collect_submodules('rapidocr_onnxruntime')

# RapidOCR 모델 데이터 수집
rapidocr_datas = collect_data_files('rapidocr_onnxruntime')

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
        ('models', 'models'),  # 🔥 [중요] 한국어 모델(det/rec/dict) 폴더 포함
    ] + rapidocr_datas,  # RapidOCR 기본 파일 포함 (안전망)
    hiddenimports=rapidocr_hidden_imports + jaraco_imports + rapidocr_submodules,
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
        
        # ===== 🔥 대용량 불필요 라이브러리 완전 제거 =====
        'tensorflow',       # 완전 불필요
        'keras',            # TensorFlow 의존성
        'h5py',             # TensorFlow 의존성
        'tensorboard',      # TensorFlow 의존성
        'torch',            # PyTorch 제거 (315MB 절감)
        'torchvision',      # PyTorch 제거
        
        # ===== PaddleOCR/PaddleX 완전 제거 =====
        'paddleocr',        # PaddleOCR 제거
        'paddlex',          # PaddleX 제거
        'paddle',           # PaddlePaddle 제거
        
        # ===== 기타 =====
        'pytesseract',      # Tesseract 제거
        'easyocr',          # EasyOCR 제거
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