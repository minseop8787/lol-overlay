# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        # ( '원본파일경로', '빌드내저장경로' )
        ('augments_global_ko.json', '.'),
        ('augment_mapping_full.txt', '.'),
        ('game_data.db', '.'),
        ('Tesseract-OCR', 'Tesseract-OCR'),
        ('assets', 'assets'),
        ('data', 'data'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pandas', 'scipy'], # 용량 줄이기 위해 제외
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
    console=True, # 디버깅을 위해 True (배포 시 검은 창이 싫으면 False로 변경)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles, # 🔥 [중요 수정] 이 부분이 빠져있어서 추가했습니다.
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='lol_api',
)