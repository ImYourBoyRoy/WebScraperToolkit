@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0status_server.ps1"
exit /b %ERRORLEVEL%
