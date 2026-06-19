@echo off
setlocal EnableDelayedExpansion

REM ============================================================
REM run_notepad_di_tests.bat
REM
REM Sets up an isolated Python venv, installs dependencies, and
REM runs the full Notepad.exe data integrity validation suite
REM (notepad_di_validator.py).
REM
REM FIX (v1.1): All python calls after venv creation now use the
REM EXPLICIT venv python path (%VENV_PYTHON%) rather than the bare
REM "python" command, which can resolve to a different interpreter
REM (e.g. a Hermes agent venv, a conda env, or a system Python)
REM if that interpreter's Scripts folder appears earlier on PATH.
REM
REM Usage:
REM   run_notepad_di_tests.bat                 -> full automated suite
REM   run_notepad_di_tests.bat --large-files    -> also include DI-18/19
REM   run_notepad_di_tests.bat --case DI-09     -> single case
REM   (any extra args are forwarded to notepad_di_validator.py)
REM ============================================================

set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "REPORT_FILE=%SCRIPT_DIR%notepad_di_report.json"
set "WORKDIR=%SCRIPT_DIR%notepad_di_workdir"

echo ============================================================
echo  Notepad.exe Data Integrity Validator - Setup and Run v1.1
echo ============================================================
echo.

REM ---- 0. Sanity checks ------------------------------------------
if /I not "%OS%"=="Windows_NT" (
    echo ERROR: This script must be run on Windows.
    exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python was not found on PATH.
    echo Install Python 3.9+ from https://www.python.org/downloads/
    echo and ensure "Add python.exe to PATH" is checked during install.
    exit /b 1
)

if not exist "%SCRIPT_DIR%notepad_di_validator.py" (
    echo ERROR: notepad_di_validator.py not found in %SCRIPT_DIR%
    echo Place this batch file in the same folder as the validator scripts.
    exit /b 1
)

REM ---- 1. Create venv if it doesn't already exist ----------------
if exist "%VENV_PYTHON%" (
    echo [1/4] Virtual environment already exists, skipping creation.
) else (
    echo [1/4] Creating virtual environment at "%VENV_DIR%" ...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        exit /b 1
    )
    if not exist "%VENV_PYTHON%" (
        echo ERROR: venv created but python.exe not found at expected path:
        echo        %VENV_PYTHON%
        exit /b 1
    )
)
echo.

REM ---- Confirm the interpreter we are actually using -------------
echo      Using interpreter: %VENV_PYTHON%
"%VENV_PYTHON%" --version
echo.

REM ---- 2. Install/upgrade dependencies (no activate needed) ------
echo [2/4] Upgrading pip inside the venv ...
"%VENV_PYTHON%" -m pip install --upgrade pip --quiet
echo.

echo [3/4] Installing dependencies (pywinauto, pywin32) ...
if exist "%SCRIPT_DIR%requirements.txt" (
    "%VENV_PYTHON%" -m pip install -r "%SCRIPT_DIR%requirements.txt"
) else (
    "%VENV_PYTHON%" -m pip install pywinauto pywin32
)
if errorlevel 1 (
    echo ERROR: pip install failed. See output above for details.
    exit /b 1
)
echo.

REM ---- Verify pywinauto is importable in THIS venv ---------------
"%VENV_PYTHON%" -c "import pywinauto; print('pywinauto', pywinauto.__version__, 'confirmed in venv')"
if errorlevel 1 (
    echo ERROR: pywinauto still not importable after install - something is wrong
    echo        with the venv. Delete the "%VENV_DIR%" folder and re-run.
    exit /b 1
)
echo.

REM ---- 4. Run the validator suite --------------------------------
echo [4/4] Running the data integrity validation suite ...
echo      Workdir: %WORKDIR%
echo      Report:  %REPORT_FILE%
echo.

"%VENV_PYTHON%" "%SCRIPT_DIR%notepad_di_validator.py" --workdir "%WORKDIR%" --report "%REPORT_FILE%" %*
set "TEST_EXIT_CODE=%ERRORLEVEL%"

echo.
echo ============================================================
if "%TEST_EXIT_CODE%"=="0" (
    echo  RESULT: All Critical-priority cases passed.
) else (
    echo  RESULT: One or more Critical-priority cases FAILED.
    echo  See %REPORT_FILE% and the console output above for details.
)
echo ============================================================

endlocal
exit /b %TEST_EXIT_CODE%
