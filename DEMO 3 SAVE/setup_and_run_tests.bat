@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo    NOTEPAD TEST AUTOMATION SUITE
echo ===================================================
echo.

echo [1/5] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH!
    echo.
    echo Please install Python from: https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "delims=" %%i in ('python --version 2^>^&1') do set "PY_VERSION=%%i"
echo Found: %PY_VERSION%
echo.

echo [2/5] Setting up virtual environment...
set "VENV_DIR=notepad_test_venv"

if exist "%VENV_DIR%" (
    echo Virtual environment already exists.
    set /p OVERWRITE="Recreate it? (y/N): "
    if /i "!OVERWRITE!"=="y" (
        echo Removing existing virtual environment...
        rmdir /s /q "%VENV_DIR%"
        python -m venv "%VENV_DIR%"
        echo Virtual environment recreated
    ) else (
        echo Using existing virtual environment
    )
) else (
    echo Creating new virtual environment...
    python -m venv "%VENV_DIR%"
    echo Virtual environment created
)

if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo ERROR: Failed to create virtual environment!
    pause
    exit /b 1
)

echo.

echo [3/5] Activating virtual environment...
call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment!
    pause
    exit /b 1
)
echo Virtual environment activated
echo.

echo [4/5] Installing required packages...
echo Upgrading pip...
python -m pip install --upgrade pip --quiet

echo Installing pywinauto...
pip install pywinauto --quiet
if errorlevel 1 (
    echo Retrying installation...
    pip install pywinauto --no-cache-dir
    if errorlevel 1 (
        echo ERROR: Failed to install pywinauto!
        echo Please check your internet connection.
        pause
        exit /b 1
    )
)
echo Packages installed successfully
echo.

echo [5/5] Running Notepad Save Button Tests...
echo ===================================================
echo.

if not exist "notepad_test.py" (
    echo ERROR: notepad_test.py not found!
    echo.
    echo Please make sure notepad_test.py is in this folder:
    echo %CD%
    echo.
    pause
    exit /b 1
)

python notepad_test.py

if errorlevel 1 (
    echo.
    echo Tests completed with errors.
) else (
    echo.
    echo All tests completed successfully!
)

echo.
echo ===================================================
echo.
echo What would you like to do next?
echo.
echo [1] Keep virtual environment active
echo [2] Deactivate and exit
echo [3] Delete virtual environment and exit
echo.
set /p CHOICE="Enter your choice (1-3): "

if "!CHOICE!"=="1" (
    echo.
    echo Virtual environment is still active.
    echo To run tests again: python notepad_test.py
    echo To deactivate later: deactivate
    cmd /k
) else if "!CHOICE!"=="3" (
    echo Removing virtual environment...
    cd /d "%~dp0"
    rmdir /s /q "%VENV_DIR%"
    echo Virtual environment removed.
    deactivate 2>nul
    echo.
    pause
) else (
    deactivate 2>nul
    echo.
    pause
)

exit /b 0
