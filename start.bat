@echo off
title DictaDesk
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo ============================================================
    echo   DictaDesk is not set up yet
    echo ============================================================
    echo.
    echo  Running install.bat for you now. Please wait...
    echo  This also runs if .venv was deleted or broken.
    echo.
    call "%~dp0install.bat" nolaunch
    if errorlevel 1 (
        echo.
        echo Setup did not finish. Fix the errors above, then run start.bat again.
        pause
        exit /b 1
    )
    if not exist ".venv\Scripts\python.exe" (
        echo.
        echo Setup finished but .venv is still missing. Run install.bat manually.
        pause
        exit /b 1
    )
)

echo.
echo ============================================================
echo   DictaDesk
echo ============================================================
echo.
echo  Starting... In Control mode press F9 to speak.
echo  Main menu option 3 = Self-check if something feels wrong.
echo.
echo ============================================================
echo.

call ".venv\Scripts\python.exe" voice_control.py
set APP_EXIT=%ERRORLEVEL%

echo.
if not "%APP_EXIT%"=="0" (
    echo DictaDesk stopped with an error. See messages above.
    echo If Piper is missing, run install.bat again with internet on.
)
pause
exit /b %APP_EXIT%
