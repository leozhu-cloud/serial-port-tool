# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.building.build_main import BUNDLE, EXE, COLLECT, PYZ, Analysis


block_cipher = None

# ------------------------------
# 收集所有 hidden imports（可选，保证打包完整）
# ------------------------------
hidden_imports = collect_submodules('SimulatedHSM')

# ------------------------------
# Analysis
# ------------------------------
a = Analysis(
    ['ui/ui.py'],
    pathex=['.'],
    binaries=[],
    datas=[('SimulatedHSM', 'SimulatedHSM')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ------------------------------
# EXE
# ------------------------------
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='KeyTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch='arm64',
    codesign_identity=None,
    entitlements_file=None,
)

# ------------------------------
# COLLECT
# ------------------------------
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='KeyTool',
)


# ------------------------------
# macOS GUI Bundle
# ------------------------------
app = BUNDLE(
    coll,
    name='KeyTool.app',
    icon='KeyTool.icns',    # 图标文件必须在 Tool/ 下
    bundle_identifier='com.alphaz.keytool',
    plist={
        'CFBundleName': 'KeyTool',
        'CFBundleDisplayName': 'KeyTool',
        'CFBundlePackageType': 'APPL',
        'CFBundleInfoDictionaryVersion': '6.0',
        'NSHighResolutionCapable': True,
        'CFBundleVersion': '1.2.0',             # 内部版本号
        'CFBundleShortVersionString': '1.2.0',  # 显示给用户的版本号
        'CFBundleIconFile': 'KeyTool.icns',
    },
)
