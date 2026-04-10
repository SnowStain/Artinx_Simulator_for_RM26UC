@echo off
echo 启动 RoboMaster 行为编辑器...
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe behavior_editor.py
) else (
  echo 未找到项目虚拟环境 .venv 。
  echo 请先运行 setup_windows_env.bat 3.13 或 setup_windows_env.bat 3.12
  exit /b 1
)
pause