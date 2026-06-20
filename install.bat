@echo off
title DictaDesk Setup
cd /d "%~dp0"
echo.
echo DictaDesk - Running automated setup...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
set EXITCODE=%ERRORLEVEL%
echo.
if not "%EXITCODE%"=="0" (
    echo Setup failed with error code %EXITCODE%.
)
pause
exit /b %EXITCODE%
