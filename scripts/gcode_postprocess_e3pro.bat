@echo off
setlocal
set "SCRIPT=%~dp0gcode_postprocess.py"
if not exist "%SCRIPT%" (
    echo ERROR: gcode_postprocess.py not found beside this .bat: "%SCRIPT%" >&2
    exit /b 1
)
where python >nul 2>&1 && python "%SCRIPT%" --printer e3pro %* && exit /b %ERRORLEVEL%
where py >nul 2>&1 && py -3 "%SCRIPT%" --printer e3pro %* && exit /b %ERRORLEVEL%
echo ERROR: Python not found. Install Python 3.11+ and ensure python is on PATH. >&2
exit /b 1
