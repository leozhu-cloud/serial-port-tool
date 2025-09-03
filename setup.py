from setuptools import setup

APP = ['ui/ui.py']   # 入口文件
DATA_FILES = []
OPTIONS = {
    'argv_emulation': True,
    'packages': ['SimulatedHSM'],
    # 'iconfile': 'app.icns',  # 可选：app图标
}

setup(
    name='KeyTool',   # 👈 应用名字
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)