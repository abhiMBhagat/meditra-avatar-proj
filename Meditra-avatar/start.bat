@echo off
echo 🚀 Starting Meditra Avatar Setup...

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Error: Python is not installed or not in PATH
    echo Please install Python 3.10+ and try again
    pause
    exit /b 1
)

REM Run setup
echo 📦 Running setup...
python setup.py
if errorlevel 1 (
    echo ❌ Setup failed
    pause
    exit /b 1
)

REM Start the server
echo 🌐 Starting server...
python run.py