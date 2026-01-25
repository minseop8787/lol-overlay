# -*- mode: python ; coding: utf-8 -*-
# lol_api.spec - PaddleOCR 전용 버전 (Tesseract 완전 제거)
# ============================================================
# 변경사항:
# 1. Tesseract-OCR 폴더 제거 (40MB+ 절감)
# 2. PaddleOCR Hidden Imports 최적화
# 3. 불필요한 라이브러리 제외 목록 확장
# ============================================================

block_cipher = None

# =========================
# PaddleOCR/PaddlePaddle Hidden Imports
# =========================
# PaddlePaddle은 동적으로 모듈을 로드하므로 명시적 선언 필요
paddle_hidden_imports = [
    # PaddlePaddle Core
    'paddle',
    'paddle.base',
    'paddle.base.core',
    'paddle.fluid',
    'paddle.nn',
    'paddle.optimizer',
    'paddle.vision',
    'paddle.utils',
    
    # PaddleOCR
    'paddleocr',
    'paddleocr.paddleocr',
    
    # PaddleX (PP-OCRv5 사용 시)
    'paddlex',
    
    # 이미지 처리 관련
    'PIL',
    'PIL.Image',
    'skimage',
    'skimage.transform',
    
    # 기하학 연산
    'shapely',
    'shapely.geometry',
    'pyclipper',
    
    # 기타 의존성
    'lmdb',
    'imgaug',
    'yaml',
    'attrdict',
]

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
        
        # ===== Tesseract 제거됨 =====
        # ('Tesseract-OCR', 'Tesseract-OCR'),  # 🔥 삭제 (40MB 절감)
        
        # ===== PaddleOCR 모델 (선택사항) =====
        # 모델은 첫 실행 시 자동 다운로드되므로 번들링 불필요
        # 오프라인 배포가 필요한 경우에만 아래 주석 해제:
        # (os.path.expanduser('~/.paddlex/official_models/korean_PP-OCRv5_mobile_rec'), 
        #  'paddlex_models/korean_PP-OCRv5_mobile_rec'),
    ],
    hiddenimports=paddle_hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # ===== 용량 최적화: 불필요한 라이브러리 제외 =====
        'pandas',           # 데이터프레임 불필요
        'scipy',            # 과학 계산 불필요
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
        'setuptools',       # 패키징 도구 불필요 (런타임)
        
        # ===== Tesseract 관련 완전 제거 =====
        'pytesseract',      # 🔥 Tesseract 바인딩 제거
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