@echo off
echo 导出机器人竞赛场地 3D 资产包...
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe build_robot_venue_map_asset.py %*
) else (
  echo 未找到项目虚拟环境 .venv 。
  echo 请先运行 setup_windows_env.bat 3.13 或 setup_windows_env.bat 3.12
  exit /b 1
)
pause