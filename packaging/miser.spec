# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Miser v1.4 (Phase 1 #6)
# Build: pyinstaller miser.spec
# Output: dist/miser (Linux/macOS) or dist/miser.exe (Windows)

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['miser.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('memory.json', '.'),
        ('embeddings.json', '.'),
    ],
    hiddenimports=[
        'flask', 'requests', 'rich', 're', 'threading',
        'model_adapter', 'memory', 'tools', 'prefetch',
        'condenser', 'quality', 'adaptive', 'task_queue', 'security',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='miser',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas,
               strip=False, upx=True, upx_exclude=[], name='miser')
