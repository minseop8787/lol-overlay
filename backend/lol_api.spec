# -*- mode: python ; coding: utf-8 -*-
# lol_api.spec - PaddleOCR 지원 버전

block_cipher = None

# =========================
# PaddleOCR Hidden Imports
# =========================
# PaddlePaddle와 PaddleOCR은 동적으로 모듈을 로드하므로
# PyInstaller가 자동으로 찾지 못하는 모듈들을 명시해야 합니다.
paddle_hidden_imports = [
    'paddle',
    'paddle.fluid',
    'paddle.nn',
    'paddle.optimizer',
    'paddleocr',
    'skimage',
    'skimage.transform',
    'PIL',
    'PIL.Image',
    'shapely',
    'shapely.geometry',
    'pyclipper',
    'lmdb',
    'imgaug',
]

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        # 기존 데이터
        ('augments_global_ko.json', '.'),
        ('augment_mapping_full.txt', '.'),
        ('game_data.db', '.'),
        ('assets', 'assets'),
        ('data', 'data'),
        # Tesseract 폴백용 (필요시 제거 가능)
        ('Tesseract-OCR', 'Tesseract-OCR'),
    ],
    hiddenimports=paddle_hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'pandas',
        'scipy',
        'matplotlib',   # 용량 줄이기
        'tkinter',      # 불필요
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
    console=True,  # 디버깅용 (배포 시 False)
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