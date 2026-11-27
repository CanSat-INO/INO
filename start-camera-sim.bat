@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0camera-simu.ps1" -Action start
if errorlevel 1 pause
