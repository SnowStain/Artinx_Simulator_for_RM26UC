@echo off
setlocal
cd /d "%~dp0"

if /I "%~1"=="-h" goto :usage
if /I "%~1"=="--help" goto :usage
if /I "%~1"=="help" goto :usage

set "PYTHON_EXE="
set "REQUESTED=%~1"

if defined REQUESTED (
    if exist "%REQUESTED%" (
        set "PYTHON_EXE=%REQUESTED%"
    ) else (
        for /f "delims=" %%i in ('py -%REQUESTED% -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%i"
    )
) else (
    for /f "delims=" %%i in ('py -3.13 -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%i"
    if not defined PYTHON_EXE (
        for /f "delims=" %%i in ('py -3.12 -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%i"
    )
)

if not defined PYTHON_EXE (
    echo 未找到可用的 Python 3.13 或 3.12 解释器。
    echo.
    echo 可选方式:
    echo   1. 安装 Python 3.13 或 3.12，并确保 py launcher 可用
    echo   2. 直接传入 python.exe 绝对路径，例如:
    echo      setup_windows_env.bat C:\Users\kylin\AppData\Local\Programs\Python\Python312\python.exe
    exit /b 1
)

echo 使用解释器: %PYTHON_EXE%
"%PYTHON_EXE%" -c "import sys; assert sys.version_info[:2] in ((3, 12), (3, 13)), f'unsupported:{sys.version}'" 1>nul 2>nul
if errorlevel 1 (
    echo 当前解释器不是 Python 3.12 或 3.13，请更换解释器后重试。
    exit /b 1
)

if exist ".venv\Scripts\python.exe" (
    echo 检测到现有 .venv，将覆盖为新的 3.12/3.13 环境。
    rmdir /s /q ".venv"
)

echo 创建虚拟环境...
"%PYTHON_EXE%" -m venv .venv
if errorlevel 1 exit /b 1

echo 升级 pip/setuptools/wheel...
".venv\Scripts\python.exe" -m pip install -U pip setuptools wheel
if errorlevel 1 exit /b 1

echo 安装项目依赖...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo.
echo 环境已完成。
echo 当前解释器:
".venv\Scripts\python.exe" -c "import sys; print(sys.executable); print(sys.version)"
echo.
echo 启动方式:
echo   .venv\Scripts\python.exe simulator.py
echo   .venv\Scripts\python.exe terrain_editor.py
exit /b 0

:usage
echo 用法:
echo   setup_windows_env.bat
echo   setup_windows_env.bat 3.13
echo   setup_windows_env.bat 3.12
echo   setup_windows_env.bat C:\Path\To\python.exe
exit /b 0