@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 > nul

set "IS_ARM64="
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "IS_ARM64=1"
if /i "%PROCESSOR_ARCHITEW6432%"=="ARM64" set "IS_ARM64=1"

REM 64-bit x86 host detection (also true for 32-bit shells running on x64 Windows via WOW64).
set "IS_X64HOST="
if /i "%PROCESSOR_ARCHITECTURE%"=="AMD64" set "IS_X64HOST=1"
if /i "%PROCESSOR_ARCHITEW6432%"=="AMD64" set "IS_X64HOST=1"

REM Required interpreter platform: ARM64 and x64 hosts use win-amd64 (no win_arm64 wheels are bundled),
REM true 32-bit hosts use win32. Required version is an exact match on 3.14.9.
set "REQ_PLAT=win32"
if defined IS_X64HOST set "REQ_PLAT=win-amd64"
if defined IS_ARM64 set "REQ_PLAT=win-amd64"

echo ======================================================================
echo  Language Variables
echo ======================================================================
set "MSG_HEADER_TITLE=This script will verify the virtual environment and install packages."
set "MSG_RECOMMENDED_VERSION=Required Python Version: 3.14.9 (exact version)"
set "MSG_REQUIRED_PACKAGES=Required Packages: tkinterdnd2==0.6.4, xxhash==4.0.2, send2trash==2.1.0, UnityPy==1.25.4"
set "MSG_VENV_NOTICE=** Checking/Creating [.venv] virtual environment and dependencies. **"
set "MSG_INSTALLING=Installing/Updating packages from the local 'packages' folder..."
set "MSG_ERROR_HEADER=[ERROR] An error occurred during environment setup or installation."
set "MSG_ERROR_CHECK_PYTHON=- Please ensure Python 3.14.9 (exact version) is installed."
set "MSG_ERROR_HOW_TO_CHECK=-(How to check: run this in the project folder: .venv\Scripts\python.exe --version)"
set "MSG_ERROR_ADMIN=- Try running this script as an administrator."
set "MSG_RUNNING_MAIN=[Running main.py inside virtual environment...]"
set "MSG_ARM_NOTICE=[Notice] Windows on ARM: Running with 64-bit Compatibility Layer."
REM NOTE: messages echoed from inside a parenthesized block must not contain parentheses.
set "MSG_VENV_RESET=[Notice] Existing .venv does not match the required interpreter 3.14.9 / %REQ_PLAT%. Recreating it."
set "MSG_VENV_LOCKED=[ERROR] Could not remove the existing .venv folder because it is in use. Close any running instance and try again."
set "MSG_INSTALLER_RC=[Notice] Python installer returned exit code"
set "MSG_TKINTER_MISSING=[ERROR] The installed interpreter has no tkinter support. Tcl/Tk is missing."
set "MSG_APP_EXIT_ERROR=[ERROR] main.py exited with a non-zero code."
set "MSG_EXIT_PROMPT=Program finished. Press any key to exit."
set "PLAT_TMP=%TEMP%\pcr_plat_%RANDOM%%RANDOM%.txt"

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

REM --- 1. Reuse an existing .venv only when it matches the required version AND platform (fail-closed) ---
set "VENV_OK="
set "VENV_PY_VER="
set "VENV_PY_PLAT="
if exist ".venv\Scripts\python.exe" (
    for /f "tokens=2 delims= " %%v in ('".venv\Scripts\python.exe" --version 2^>nul') do (
        set "VENV_PY_VER=%%v"
    )
)
if exist ".venv\Scripts\python.exe" if "!VENV_PY_VER!"=="3.14.9" (
    ".venv\Scripts\python.exe" -c "import sysconfig;print(sysconfig.get_platform())" > "!PLAT_TMP!" 2>nul
    for /f "usebackq delims=" %%q in ("!PLAT_TMP!") do (
        set "VENV_PY_PLAT=%%q"
    )
    del /f /q "!PLAT_TMP!" >nul 2>&1
    if /i "!VENV_PY_PLAT!"=="!REQ_PLAT!" set "VENV_OK=1"
)
if exist ".venv\Scripts\python.exe" if not defined VENV_OK (
    echo  %MSG_VENV_RESET%
    rmdir /s /q ".venv" >nul 2>&1
    if exist ".venv" (
        echo.
        echo  %MSG_VENV_LOCKED%
        goto :handle_error
    )
)

REM --- 2. Locate an installed interpreter matching exactly 3.14.9 and the required platform ---
if not exist ".venv\Scripts\python.exe" (
    set "HOST_PY_EXE="

    for /f "delims=" %%p in ('py -3.14 -c "import sys,sysconfig;print((sys.executable+'|'+sysconfig.get_platform()) if sys.version_info[:3]==(3,14,9) else '')" 2^>nul') do (
        call :accept_host "%%p"
    )

    if not defined HOST_PY_EXE (
        for /f "delims=" %%p in ('python -c "import sys,sysconfig;print((sys.executable+'|'+sysconfig.get_platform()) if sys.version_info[:3]==(3,14,9) else '')" 2^>nul') do (
            call :accept_host "%%p"
        )
    )

    if not defined HOST_PY_EXE call :probe_host "%LocalAppData%\Programs\Python\Python314\python.exe"
    if not defined HOST_PY_EXE call :probe_host "%LocalAppData%\Programs\Python\Python314-32\python.exe"
    if not defined HOST_PY_EXE call :probe_host "%ProgramFiles%\Python314\python.exe"
    if not defined HOST_PY_EXE call :probe_host "%ProgramFiles%\Python314-32\python.exe"

    if not defined HOST_PY_EXE (
        if /i "!REQ_PLAT!"=="win-amd64" (
            set "PY_INSTALLER=python-3.14.9-amd64.exe"
        ) else (
            set "PY_INSTALLER=python-3.14.9.exe"
        )

        REM Download to a temporary name and promote it only after the size check passes,
        REM so an interrupted download is never mistaken for a usable installer.
        if not exist "!PY_INSTALLER!" (
            set "PY_DL_TMP=!PY_INSTALLER!.download"
            if exist "!PY_DL_TMP!" del /f /q "!PY_DL_TMP!" >nul 2>&1
            curl.exe -f -L --retry 3 --retry-delay 2 --connect-timeout 15 --progress-bar -o "!PY_DL_TMP!" "https://www.python.org/ftp/python/3.14.9/!PY_INSTALLER!"
            set "PY_DL_RC=!errorlevel!"
            if not "!PY_DL_RC!"=="0" (
                if exist "!PY_DL_TMP!" del /f /q "!PY_DL_TMP!" >nul 2>&1
                goto :handle_error
            )
            set "PY_DL_SIZE="
            for %%A in ("!PY_DL_TMP!") do set "PY_DL_SIZE=%%~zA"
            if not defined PY_DL_SIZE goto :handle_error
            if !PY_DL_SIZE! LSS 10000000 (
                if exist "!PY_DL_TMP!" del /f /q "!PY_DL_TMP!" >nul 2>&1
                goto :handle_error
            )
            move /y "!PY_DL_TMP!" "!PY_INSTALLER!" >nul 2>&1
            if not exist "!PY_INSTALLER!" goto :handle_error
        )

        start /wait "" "!PY_INSTALLER!" /passive InstallAllUsers=0 PrependPath=0 Include_test=0 Include_pip=1 Include_launcher=0
        set "PY_INST_RC=!errorlevel!"
        if exist "!PY_INSTALLER!" del /f /q "!PY_INSTALLER!" >nul 2>&1
        if not "!PY_INST_RC!"=="0" echo  %MSG_INSTALLER_RC% !PY_INST_RC!

        call :probe_host "%LocalAppData%\Programs\Python\Python314\python.exe"
        if not defined HOST_PY_EXE call :probe_host "%LocalAppData%\Programs\Python\Python314-32\python.exe"
        if not defined HOST_PY_EXE goto :handle_error
    )

    REM --- 3. Create the virtual environment (abort loudly when a stale one cannot be removed) ---
    if exist ".venv" rmdir /s /q ".venv" >nul 2>&1
    if exist ".venv" (
        echo.
        echo  %MSG_VENV_LOCKED%
        goto :handle_error
    )
    "!HOST_PY_EXE!" -m venv .venv
    if not exist ".venv\Scripts\python.exe" goto :handle_error

    ".venv\Scripts\python.exe" -c "import tkinter" >nul 2>&1
    if errorlevel 1 (
        echo.
        echo  %MSG_TKINTER_MISSING%
        goto :handle_error
    )
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
if defined IS_ARM64 echo  %MSG_ARM_NOTICE%
echo ======================================================================
echo.
.venv\Scripts\python.exe main.py
if errorlevel 1 echo  %MSG_APP_EXIT_ERROR%
goto :end_script


:probe_host
REM %~1 = python.exe path. Verify exact version 3.14.9 and the required platform before accepting it.
if not exist "%~1" exit /b 0
"%~1" -c "import sys,sysconfig;print((sys.executable+'|'+sysconfig.get_platform()) if sys.version_info[:3]==(3,14,9) else '')" > "!PLAT_TMP!" 2>nul
for /f "usebackq delims=" %%p in ("!PLAT_TMP!") do (
    call :accept_host "%%p"
)
del /f /q "!PLAT_TMP!" >nul 2>&1
exit /b 0


:accept_host
REM %~1 = "<python.exe>|<sysconfig platform>"; accept only the platform required for this host.
for /f "tokens=1,2 delims=|" %%a in ("%~1") do (
    if "%%~b"=="" exit /b 0
    if /i not "%%~b"=="!REQ_PLAT!" exit /b 0
    if exist "%%~a" set "HOST_PY_EXE=%%~a"
)
exit /b 0


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
