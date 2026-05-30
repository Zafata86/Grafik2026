@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
echo =====================================================
echo   ГРАФИК - у-к Автоматизация
echo =====================================================
echo.

pip install flask --quiet

if not exist database.db (
    echo Инициализация на базата данни...
    python init_db.py
    echo.
)

echo Приложението стартира на: http://localhost:5000
echo Натиснете Ctrl+C за спиране.
echo.
start "" http://localhost:5000
python app.py
pause
