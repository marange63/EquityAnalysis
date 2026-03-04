@echo off
call "C:\Users\wamfo\anaconda3\Scripts\activate.bat" Finance
if errorlevel 1 (
    echo Failed to activate conda environment "Finance"
    pause
    exit /b 1
)
cd /d "%~dp0"
python main.py
if errorlevel 1 (
    echo.
    echo Application exited with an error.
    pause
)
