@echo off
setlocal EnableDelayedExpansion
title DictaDesk Setup
cd /d "%~dp0"

echo.
echo ============================================================
echo   DictaDesk - First-time setup
echo ============================================================
echo.
echo  This runs ONCE. It downloads and installs everything DictaDesk
echo  needs. You need Python 3.10+ installed first (python.org).
echo.
echo  During Python install, check:  Add Python to PATH
echo.
echo  Estimated time: 5-20 minutes depending on your internet.
echo  See GETTING_STARTED.txt for a full plain-English guide.
echo.
echo ============================================================
echo.
pause

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
set EXITCODE=%ERRORLEVEL%

echo.
if "%EXITCODE%"=="0" (
    echo ============================================================
    echo   Setup finished successfully!
    echo ============================================================
    echo.
    echo  Next: double-click start.bat every time you want DictaDesk.
    echo  Tip: read GETTING_STARTED.txt for first-run menu choices.
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
    echo  Common fixes:
    echo    - Install Python 3.12 from python.org with Add to PATH
    echo    - Run this window as Administrator if downloads fail
    echo    - Check GETTING_STARTED.txt troubleshooting section
    echo.
)

pause
exit /b %EXITCODE%
