@echo off
echo 启动 RoboMaster 2026 哨兵模拟器...
if exist .venv\Scripts\python.exe (
	.venv\Scripts\python.exe simulator.py
) else (
	python simulator.py
)
pause
