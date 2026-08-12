@echo off
chcp 65001 >nul
title 证券业 AI 日报 - 本地采集（直连本机 IP）
echo ============================================================
echo   证券业 AI 动态日报 —— 本地采集
echo   用你本机 IP 运行，绕开沙箱共享出口 IP 限流
echo ============================================================
echo.

REM 定位脚本所在目录（无论从哪里双击都能找到 collect.py）
set "SCRIPT_DIR=%~dp0"
set "PYTHON_EXE="

REM 1) 优先使用系统 Python（推荐，走你自己的宽带/公司 IP）
where python >nul 2>nul
if %errorlevel%==0 (
  set "PYTHON_EXE=python"
  goto :run
)

REM 2) 退回 WorkBuddy 内置 Python（路径若不存在会提示）
set "WB_PY=C:\Users\songjianan_dfc\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if exist "%WB_PY%" (
  set "PYTHON_EXE=%WB_PY%"
  goto :run
)

echo [错误] 未找到 Python。请安装 Python 3.10+（勾选 Add to PATH）后重试。
pause
exit /b 1

:run
echo 使用 Python：%PYTHON_EXE%
echo 工作目录：%SCRIPT_DIR%
echo.
cd /d "%SCRIPT_DIR%"
"%PYTHON_EXE%" collect.py
set "RC=%errorlevel%"
echo.
if %RC%==0 (
  echo 采集完成。新数据已写入 site/data/data.json
  echo 回到对话窗口，对我说「发布」或「部署」，我会把更新后的站点推送到线上。
) else (
  echo 采集脚本异常退出（错误码 %RC%）。请把上方红字发给我排查。
)
echo.
pause
