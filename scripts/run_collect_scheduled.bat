@echo off
chcp 65001 >nul
REM 静默版采集（供 Windows 任务计划程序调用，不弹窗、不 pause，输出追加到 collect_log.txt）
set "SCRIPT_DIR=%~dp0"
set "LOG=%SCRIPT_DIR%collect_log.txt"
set "PYTHON_EXE="

where python >nul 2>nul
if %errorlevel%==0 ( set "PYTHON_EXE=python" & goto :run )

set "WB_PY=C:\Users\songjianan_dfc\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if exist "%WB_PY%" ( set "PYTHON_EXE=%WB_PY%" & goto :run )

echo [%date% %time%] [错误] 未找到 Python，采集未执行 >> "%LOG%"
exit /b 1

:run
echo [%date% %time%] ===== 开始采集（交易日判断由 collect.py 内部处理）===== >> "%LOG%"
cd /d "%SCRIPT_DIR%"
"%PYTHON_EXE%" collect.py >> "%LOG%" 2>&1
echo [%date% %time%] ===== 采集结束（退出码 %errorlevel%）===== >> "%LOG%"
exit /b %errorlevel%
