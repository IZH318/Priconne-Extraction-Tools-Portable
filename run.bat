@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 > nul

echo ======================================================================
echo  Language Variables
echo ======================================================================
set "MSG_HEADER_TITLE=This script will verify the virtual environment and install packages."
set "MSG_RECOMMENDED_VERSION=Required Python Version: 3.14.9"
set "MSG_REQUIRED_PACKAGES=Required Packages: tkinterdnd2==0.6.4, xxhash==4.0.2, send2trash==2.1.0, UnityPy==1.25.4"
set "MSG_VENV_NOTICE=** Checking/Creating [.venv] virtual environment and dependencies. **"
set "MSG_INSTALLING=Installing/Updating packages from the local 'packages' folder..."
set "MSG_ERROR_HEADER=[ERROR] An error occurred during environment setup or installation."
set "MSG_ERROR_CHECK_PYTHON=- Please ensure Python 3.14.9 is installed."
set "MSG_ERROR_HOW_TO_CHECK=-(How to check: Run 'py -3.14 --version' in your terminal)"
set "MSG_ERROR_ADMIN=- Try running this script as an administrator."
set "MSG_RUNNING_MAIN=[Running main.py inside virtual environment...]"
set "MSG_EXIT_PROMPT=Program finished. Press any key to exit."

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
echo ======================================================================

if exist ".venv\Scripts\python.exe" (
    for /f "tokens=2 delims= " %%v in ('".venv\Scripts\python.exe" --version 2^>nul') do (
        set "VENV_PY_VER=%%v"
    )
    echo !VENV_PY_VER! | findstr /b "3.14" >nul 2>&1
    if errorlevel 1 (
        rmdir /s /q ".venv" >nul 2>&1
    )
)

if not exist ".venv\Scripts\python.exe" (
    set "HOST_PY_EXE="

    for /f "delims=" %%p in ('py -3.14 -c "import sys; print(sys.executable)" 2^>nul') do (
        if exist "%%~p" set "HOST_PY_EXE=%%~p"
    )

    if not defined HOST_PY_EXE (
        for /f "delims=" %%p in ('python -c "import sys; print(sys.executable if sys.version_info[:2]==(3,14) else \"\")" 2^>nul') do (
            if exist "%%~p" set "HOST_PY_EXE=%%~p"
        )
    )

    if not defined HOST_PY_EXE (
        if exist "%LocalAppData%\Programs\Python\Python314\python.exe" set "HOST_PY_EXE=%LocalAppData%\Programs\Python\Python314\python.exe"
        if exist "%LocalAppData%\Programs\Python\Python314-32\python.exe" set "HOST_PY_EXE=%LocalAppData%\Programs\Python\Python314-32\python.exe"
        if exist "%LocalAppData%\Programs\Python\Python314-arm64\python.exe" set "HOST_PY_EXE=%LocalAppData%\Programs\Python\Python314-arm64\python.exe"
    )

    if not defined HOST_PY_EXE (
        if exist "%ProgramFiles%\Python314\python.exe" set "HOST_PY_EXE=%ProgramFiles%\Python314\python.exe"
        if exist "%ProgramFiles%\Python314-32\python.exe" set "HOST_PY_EXE=%ProgramFiles%\Python314-32\python.exe"
        if exist "%ProgramFiles%\Python314-arm64\python.exe" set "HOST_PY_EXE=%ProgramFiles%\Python314-arm64\python.exe"
    )

    if not defined HOST_PY_EXE (
        set "SYS_ARCH=%PROCESSOR_ARCHITECTURE%"
        
        if /i "!SYS_ARCH!"=="AMD64" (
            set "PY_INSTALLER=python-3.14.9-amd64.exe"
        ) else if /i "!SYS_ARCH!"=="ARM64" (
            set "PY_INSTALLER=python-3.14.9-arm64.exe"
        ) else if /i "!SYS_ARCH!"=="x86" (
            set "PY_INSTALLER=python-3.14.9.exe"
        ) else (
            goto :handle_error
        )

        if not exist "!PY_INSTALLER!" (
            curl.exe -L --progress-bar -o "!PY_INSTALLER!" "https://www.python.org/ftp/python/3.14.9/!PY_INSTALLER!"
            if errorlevel 1 goto :handle_error
        )
        
        start /wait "" "!PY_INSTALLER!" /passive InstallAllUsers=0 PrependPath=0 Include_test=0 Include_pip=1 Include_launcher=0
        if exist "!PY_INSTALLER!" del /f /q "!PY_INSTALLER!" >nul 2>&1
        
        if exist "%LocalAppData%\Programs\Python\Python314\python.exe" (
            set "HOST_PY_EXE=%LocalAppData%\Programs\Python\Python314\python.exe"
        ) else if exist "%LocalAppData%\Programs\Python\Python314-32\python.exe" (
            set "HOST_PY_EXE=%LocalAppData%\Programs\Python\Python314-32\python.exe"
        ) else if exist "%LocalAppData%\Programs\Python\Python314-arm64\python.exe" (
            set "HOST_PY_EXE=%LocalAppData%\Programs\Python\Python314-arm64\python.exe"
        ) else (
            goto :handle_error
        )
    )

    if exist ".venv" rmdir /s /q ".venv" >nul 2>&1
    "!HOST_PY_EXE!" -m venv .venv
    if not exist ".venv\Scripts\python.exe" goto :handle_error
)

echo.
echo ======================================================================
echo  %MSG_INSTALLING%
echo ======================================================================
echo.

set "LINKS_ARGS=--find-links="./packages""
for /f "delims=" %%i in ('dir /b /s /ad "packages" 2^>nul') do (
    set "REL_PATH=%%i"
    set "REL_PATH=!REL_PATH:%~dp0=./!"
    set "REL_PATH=!REL_PATH:\=/!"
    set "LINKS_ARGS=!LINKS_ARGS! --find-links="!REL_PATH!""
)

.venv\Scripts\python.exe -m pip install --no-index !LINKS_ARGS! -r requirements.txt

if errorlevel 1 goto :handle_error
goto :handle_success


:handle_success
echo.
echo ======================================================================
echo  %MSG_RUNNING_MAIN%
echo ======================================================================
echo.
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
echo ======================================================================
echo  %MSG_EXIT_PROMPT%
echo ======================================================================
pause >nul
exit