@echo off
chcp 65001 >nul
if not exist "%~dp0app\main.py" exit /b 1
if not exist "%~dp0data\bank.json" exit /b 1
if not exist "%~dp0scripts\reset_records.py" exit /b 1
set "PY=D:\software\anaconda\python.exe"
if defined VOCABAPP_PYTHON set "PY=%VOCABAPP_PYTHON%"
if not exist "%PY%" (
  echo 找不到 Python。请设置 VOCABAPP_PYTHON 为启动插件使用的 python.exe 完整路径。
  pause
  exit /b 1
)
"%PY%" -B "%~dp0scripts\reset_records.py" %*
set "RC=%ERRORLEVEL%"
pause
exit /b %RC%
