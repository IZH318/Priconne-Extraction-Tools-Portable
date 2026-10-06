@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 > nul

echo ======================================================================
echo Language Variables
echo ======================================================================
set "MSG_HEADER_TITLE=This script will verify the virtual environment and install packages."
set "MSG_RECOMMENDED_VERSION=Recommended Python Version: 3.10.11"
set "MSG_REQUIRED_PACKAGES=Required Packages: tkinterdnd2, xxhash, send2trash, UnityPy"
set "MSG_VENV_NOTICE=** Checking/Creating [.venv] virtual environment and dependencies. **"
set "MSG_INSTALLING=Installing/Updating packages from the local 'packages' folder..."
set "MSG_ERROR_HEADER=[ERROR] An error occurred during environment setup or installation."
set "MSG_ERROR_CHECK_PYTHON=- Please ensure Python 3.10 is installed AND set as default."
set "MSG_ERROR_HOW_TO_CHECK=-(How to check: Run 'py --version' or 'python --version' in your terminal)"
set "MSG_ERROR_ADMIN=- Try running this script as an administrator."
set "MSG_SUCCESS_HEADER=[SUCCESS] Virtual environment and all packages are fully ready."
set "MSG_RUN_PROMPT=Press any key to execute main.py in the virtual environment."
set "MSG_RUNNING_MAIN=[Running main.py inside virtual environment...]"
set "MSG_EXIT_PROMPT=Program finished. Press any key to exit."

echo ======================================================================
echo Main Installation Logic
echo ======================================================================
:main_install
cls
echo.
echo ======================================================================
echo  %MSG_HEADER_TITLE%
echo ======================================================================
echo.
echo  %MSG_RECOMMENDED_VERSION%
echo.
echo  %MSG_REQUIRED_PACKAGES%
echo.
echo  %MSG_VENV_NOTICE%
echo.

if not exist ".venv\Scripts\python.exe" (
    if exist ".venv" rmdir /s /q ".venv" >nul 2>&1
    py -3.10 -m venv .venv 2>nul || py -m venv .venv 2>nul || python -m venv .venv
    if not exist ".venv\Scripts\python.exe" goto :handle_error
)

echo  %MSG_INSTALLING%
echo.

set "LINKS_ARGS=--find-links=./packages"
for /f "delims=" %%i in ('dir /b /s /ad "packages" 2^>nul') do (
    set "REL_PATH=%%i"
    set "REL_PATH=!REL_PATH:%~dp0=./!"
    set "REL_PATH=!REL_PATH:\=/!"
    set "LINKS_ARGS=!LINKS_ARGS! --find-links=!REL_PATH!"
)

.venv\Scripts\python.exe -m pip install --no-index !LINKS_ARGS! -r requirements.txt

if errorlevel 1 goto :handle_error
goto :handle_success


:handle_success
echo.
echo ======================================================================
echo  %MSG_SUCCESS_HEADER%
echo ======================================================================
echo.
echo  %MSG_RUN_PROMPT%
pause >nul

cls
echo.
echo  %MSG_RUNNING_MAIN%
.venv\Scripts\python.exe main.py
goto :end_script


:handle_error
echo.
echo ======================================================================
echo  %MSG_ERROR_HEADER%
echo ======================================================================
echo.
echo  %MSG_ERROR_CHECK_PYTHON%
echo.
echo  %MSG_ERROR_HOW_TO_CHECK%
echo.
echo  %MSG_ERROR_ADMIN%
echo.
goto :end_script


:end_script
echo.
echo  %MSG_EXIT_PROMPT%
pause >nul
exit
