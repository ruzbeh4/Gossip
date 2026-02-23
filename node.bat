@echo off
setlocal
set SCRIPT_DIR=%~dp0

if exist "%SCRIPT_DIR%\.venv\Scripts\python.exe" (
  "%SCRIPT_DIR%\.venv\Scripts\python.exe" -m protocol.node %*
  exit /b %ERRORLEVEL%
)

python -m protocol.node %*
exit /b %ERRORLEVEL%
