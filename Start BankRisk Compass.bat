@echo off
setlocal
cd /d "%~dp0"
title BankRisk Compass

set "VENV_PYTHON=%CD%\.venv\Scripts\python.exe"

echo.
echo ========================================
echo        Starting BankRisk Compass
echo ========================================
echo.

if not exist "%VENV_PYTHON%" (
    echo First-time setup: creating the private Python environment...

    where py >nul 2>nul
    if not errorlevel 1 (
        py -3.13 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>nul
        if not errorlevel 1 (
            py -3.13 -m venv .venv
        ) else (
            py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>nul
            if errorlevel 1 goto :python_version
            py -3 -m venv .venv
        )
    ) else (
        where python >nul 2>nul
        if errorlevel 1 goto :python_missing

        python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)"
        if errorlevel 1 goto :python_version

        python -m venv .venv
    )

    if not exist "%VENV_PYTHON%" goto :setup_failed
)

"%VENV_PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>nul
if errorlevel 1 goto :venv_version

for %%A in (requirements-app.txt) do set "CURRENT_REQUIREMENTS_TIME=%%~tA"
set "INSTALLED_REQUIREMENTS_TIME="
if exist ".venv\.requirements-installed" set /p INSTALLED_REQUIREMENTS_TIME=<".venv\.requirements-installed"
if "%CURRENT_REQUIREMENTS_TIME%"=="%INSTALLED_REQUIREMENTS_TIME%" goto :dependencies_ready

echo Checking required packages...
"%VENV_PYTHON%" -m pip install --disable-pip-version-check -r requirements-app.txt
if errorlevel 1 goto :install_failed
> ".venv\.requirements-installed" echo %CURRENT_REQUIREMENTS_TIME%

:dependencies_ready
set "DEBUG=True"
set "SECURE_SSL_REDIRECT=False"
set "ALLOWED_HOSTS=127.0.0.1,localhost"
set "LOGIN_REQUIRED=False"

echo Preparing the local audit database...
"%VENV_PYTHON%" manage.py migrate --no-input
if errorlevel 1 goto :setup_failed
"%VENV_PYTHON%" manage.py bootstrap_roles
if errorlevel 1 goto :setup_failed

echo.
echo BankRisk Compass is opening at:
echo http://127.0.0.1:8000/
echo.
echo Keep this window open while using the application.
echo Close it or press Ctrl+C to stop the application.
echo.

if /I not "%BANKRISK_NO_BROWSER%"=="1" start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8000/'"
"%VENV_PYTHON%" manage.py runserver 127.0.0.1:8000 --noreload
goto :end

:python_missing
echo.
echo Python is not installed or is not available on PATH.
echo Install Python 3.13 from https://www.python.org/downloads/
echo During installation, select "Add Python to PATH", then run this file again.
goto :failure

:python_version
echo.
echo BankRisk Compass requires Python 3.12 or newer.
echo Install Python 3.13 from https://www.python.org/downloads/
goto :failure

:venv_version
echo.
echo The existing .venv uses an unsupported Python version.
echo Delete the .venv folder, install Python 3.13, and run this file again.
goto :failure

:setup_failed
echo.
echo The private Python environment could not be created.
goto :failure

:install_failed
echo.
echo The required packages could not be installed.
echo Check your internet connection and try again.
goto :failure

:failure
echo.
pause
exit /b 1

:end
endlocal
