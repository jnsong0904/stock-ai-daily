@echo off
chcp 65001 >nul
title 证券业 AI 日报 - 本地预览
set "PYTHON_EXE="
where python >nul 2>nul
if %errorlevel%==0 ( set "PYTHON_EXE=python" & goto :go )
set "WB_PY=C:\Users\songjianan_dfc\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if exist "%WB_PY%" ( set "PYTHON_EXE=%WB_PY%" & goto :go )
echo [错误] 未找到 Python，无法启动本地预览。
pause
exit /b 1

:go
REM 切到 site 目录启动静态服务器（data.json 经 http 加载，file:// 直接打开会被浏览器拦截）
set "SITE_DIR=%~dp0..\site"
cd /d "%SITE_DIR%"
echo 本地预览地址： http://localhost:8080
echo 在浏览器打开上面的地址即可查看日报（含竞品矩阵）。
echo 按 Ctrl+C 停止预览服务器。
echo.
"%PYTHON_EXE%" -m http.server 8080
pause
