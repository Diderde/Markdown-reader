@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\flet.exe" (
    echo [错误] 未找到虚拟环境。请先双击 run.bat 完成环境安装。
    pause
    exit /b 1
)

echo ============================================================
echo Markdown Reader - Web 模式（仅本机回环，配合 SSH 隧道使用）
echo ============================================================
echo 绑定地址: http://127.0.0.1:8550  （不暴露到局域网）
echo.
echo 手机访问方式（需先建立 SSH 隧道）:
echo   Termux:   ssh -N -L 8550:127.0.0.1:8550 用户名@本机IP
echo   然后手机浏览器打开 http://127.0.0.1:8550
echo   详细说明见 README.md 的「SSH 隧道访问」章节。
echo.

".venv\Scripts\flet.exe" run --web --host 127.0.0.1 --port 8550 main.py
