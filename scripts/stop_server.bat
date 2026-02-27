@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_server.ps1"
exit /b %ERRORLEVEL%
