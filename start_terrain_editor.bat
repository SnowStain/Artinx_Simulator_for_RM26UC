@echo off
echo 启动 RoboMaster 地图预设编辑器...
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe terrain_editor.py
) else (
  python terrain_editor.py
)
pause