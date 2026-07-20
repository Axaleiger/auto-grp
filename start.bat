@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Сборка данных...
python build_data.py
if errorlevel 1 pause & exit /b 1
echo.
echo Запуск сервера http://localhost:8765
echo Откройте: http://localhost:8765/auto_grp_analyzer.html
echo Ctrl+C — остановить
start http://localhost:8765/auto_grp_analyzer.html
python -m http.server 8765
