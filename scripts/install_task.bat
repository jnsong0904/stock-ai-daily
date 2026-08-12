@echo off
chcp 65001 >nul
REM ============================================================
REM  一键注册「证券业 AI 日报」定时采集任务
REM  右键本文件 →「以管理员身份运行」一次即可（之后全自动）
REM ============================================================
set "TASK_NAME=证券业AI日报-采集"
set "BAT=E:\个人文件夹\workbuddy-flies\2026-08-11-09-52-56\scripts\run_collect_scheduled.bat"

echo 正在注册 Windows 计划任务：%TASK_NAME%
echo 运行目标：%BAT%
echo 计划时间：每周一至周五 08:30（交易日判断由 collect.py 内部处理，非交易日自动跳过）
echo.

schtasks /create /tn "%TASK_NAME%" /tr "%BAT%" /sc weekly /d MON,TUE,WED,THU,FRI /st 08:30 /f

if %errorlevel%==0 (
  echo.
  echo [成功] 定时任务已创建。可在「任务计划程序」(taskschd.msc) 中查看/修改。
  echo   日志写入：scripts\collect_log.txt
) else (
  echo.
  echo [失败] 退出码 %errorlevel%。请「右键本文件 → 以管理员身份运行」后重试。
)
echo.
pause
