@echo off
echo 启动 RoboMaster 行为编辑器...
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe behavior_editor.py
) else (
  python behavior_editor.py
)
pause