# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=[
        'D:\\anaconda\\envs\\webscrap\\Library\\bin',  # 🔥 [필수] libffi 등 시스템 DLL 경로
        'D:\\anaconda\\envs\\webscrap\\DLLs',          # 파이썬 확장 모듈 경로
        'D:\\ML\\lol-overlay\\backend'
    ],
    binaries=[
        ('D:\\anaconda\\envs\\webscrap\\Library\\bin\\*.dll', '.') # 🔥 [핵심] Anaconda DLL 강제 포함
    ],
    datas=[
        ('assets/augments/*.png', 'assets/augments'),
        ('assets/augment_confirm_button.png', 'assets'),
        ('augment_mapping_full.txt', '.'),
        ('augments_global_ko.json', '.'),
        ('data/aram_builds.json', 'data'),
        ('shop_template.png', '.'),
        ('game_data.db', '.'),
        ('Tesseract-OCR', 'Tesseract-OCR') # 🔥 [필수] Tesseract 포함
    ],
    hiddenimports=['engineio.async_drivers.threading', 'cv2', 'numpy', 'PIL', 'mss', 'requests', 'lcu_driver', 'win32gui'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'pandas', 'notebook'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='lol_overlay',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True, # 디버깅을 위해 True 유지 (사용자는 추후 --noconsole 가능)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/augments/ADAPt.png' # 아이콘 예시
)
