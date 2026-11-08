@echo off
chcp 65001 >nul
if not exist "%~dp0app\main.py" exit /b 1
if not exist "%~dp0data\bank.json" exit /b 1
echo 请先关闭背单词插件，再按任意键清空使用记录。词库不会删除。
pause >nul
for %%F in (progress.json progress.json.tmp _win.json) do if exist "%~dp0data\%%F" del /q "%~dp0data\%%F"
for %%F in (progress.json progress.json.tmp _win.json) do if exist "%~dp0data\%%F" (echo 清空失败，请检查文件是否被占用或只读。 & pause & exit /b 1)
echo 已清空使用记录，重新打开插件即可。
pause
exit /b 0
