@echo off
title DictaDesk Setup
cd /d "%~dp0"
echo.
echo DictaDesk - Running automated setup...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
echo.
pause
