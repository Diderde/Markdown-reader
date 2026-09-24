@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title Markdown Reader - 环境检查与依赖安装

echo ============================================================
echo Markdown Reader：环境检查，缺失时经确认后自动安装依赖
echo ============================================================
echo.

set "BOOTSTRAP=%~dp0bootstrap.py"
if not exist "%BOOTSTRAP%" (
    echo [错误] 未找到 bootstrap.py
    echo 请将 run.bat、bootstrap.py、main.py 放在同一目录。
    pause
    exit /b 1
)

if not exist "%~dp0main.py" (
    echo [错误] 未找到 main.py
    echo 请将 run.bat、bootstrap.py、main.py 放在同一目录。
    pause
    exit /b 1
)

rem Any interpreter able to run bootstrap.py is enough here.
rem bootstrap.py re-scans all usable Pythons itself before creating the venv.

where py.exe >nul 2>nul
if not errorlevel 1 (
    py -3 "%BOOTSTRAP%" %*
    set "RC=!ERRORLEVEL!"
    goto :finish
)

where python.exe >nul 2>nul
if not errorlevel 1 (
    python "%BOOTSTRAP%" %*
    set "RC=!ERRORLEVEL!"
    goto :finish
)

where python3.exe >nul 2>nul
if not errorlevel 1 (
    python3 "%BOOTSTRAP%" %*
    set "RC=!ERRORLEVEL!"
    goto :finish
)

rem Fallback: well-known install locations when PATH has no python.

for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%USERPROFILE%\miniconda3\python.exe"
    "%USERPROFILE%\anaconda3\python.exe"
    "C:\Python313\python.exe"
    "D:\Python313\python.exe"
    "C:\Python312\python.exe"
    "D:\Python312\python.exe"
    "D:\python.exe"
) do (
    if exist "%%~P" (
        "%%~P" "%BOOTSTRAP%" %*
        set "RC=!ERRORLEVEL!"
        goto :finish
    )
)

echo [错误] 完全没有找到能够启动 bootstrap.py 的 Python。
echo 请先安装 64 位 Python 3.10 或更新版本（推荐 3.13），并勾选：
echo   1. pip
echo   2. py launcher
echo   3. Add Python to PATH
set "RC=1"

:finish
if not "%RC%"=="0" (
    echo.
    echo 启动失败。请打开同目录下的 environment_report.txt 查看具体原因。
    pause
)
exit /b %RC%
