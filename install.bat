@echo off
setlocal EnableDelayedExpansion
title DictaDesk Setup
cd /d "%~dp0"

echo.
echo ============================================================
echo   DictaDesk - One-click setup
echo ============================================================
echo.
echo  This runs ONCE and installs EVERYTHING automatically:
echo    - Python 3.12 (downloaded + added to PATH if missing)
echo    - Tesseract OCR + Turkish pack (downloaded + added to PATH)
echo    - All Python packages, Piper TTS, Playwright browser
echo    - The right GPU backend for YOUR card (NVIDIA / AMD / CPU)
echo.
echo  No manual steps. A Windows security prompt may appear once
echo  while installing Tesseract - click Yes.
echo.
echo  Estimated time: 5-20 minutes depending on your internet.
echo ============================================================
echo.
pause

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set EXITCODE=%ERRORLEVEL%

echo.
if "%EXITCODE%"=="0" (
    echo ============================================================
    echo   Setup finished successfully!
    echo ============================================================
    echo.
    echo  Next: double-click start.bat every time you want DictaDesk.
    echo.
    if /i not "%~1"=="nolaunch" (
        set /p LAUNCH="Start DictaDesk now? (Y/N): "
        if /i "!LAUNCH!"=="Y" call "%~dp0start.bat"
    )
) else (
    echo ============================================================
    echo   Setup failed (error code %EXITCODE%).
    echo ============================================================
    echo.
    echo  Try again with internet on. If Python could not install
    echo  automatically, install it once from python.org with
    echo  "Add python.exe to PATH", then re-run install.bat.
    echo.
)

pause
exit /b %EXITCODE%
