@echo off
:: This command ensures the script always runs in the folder where the .bat file is located
cd /d "%~dp0"

echo ========================================
echo  Mercury Tours Playwright Test Runner
echo ========================================
echo Current Directory: %CD%
echo.

:: Check if node_modules exists to ensure dependencies are installed
if not exist "node_modules\" (
    echo Dependencies not found. Installing now...
    call npm install
    if %ERRORLEVEL% NEQ 0 (
        echo ERROR: Failed to install dependencies.
        pause
        exit /b 1
    )
    echo.
)

:: Run the Playwright tests
echo Running Playwright tests in HEADED mode...
echo.
call npx playwright test --headed --reporter=list

echo.
echo ========================================
echo  Test execution complete!
echo ========================================
pause