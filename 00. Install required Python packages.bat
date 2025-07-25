@echo off
setlocal
rem --- Set the console code page to UTF-8 to support multilingual output later ---
chcp 65001 > nul

rem ======================================================================
rem Language Selection
rem ======================================================================
:select_language
cls
echo.
echo    Please select a language.
echo.
echo    =================================
echo.
echo      1. Korean
echo.
echo      2. English
echo.
echo      3. Japanese
echo.
echo    =================================
echo.
set /p lang_choice="Enter number (1-3) and press Enter: "

if "%lang_choice%"=="1" goto :set_korean
if "%lang_choice%"=="2" goto :set_english
if "%lang_choice%"=="3" goto :set_japanese

rem --- Handle invalid input ---
cls
echo.
echo    Invalid input. Please enter 1, 2, or 3.
echo.
pause
goto :select_language


rem ======================================================================
rem Set Language Variables
rem ======================================================================
:set_korean
set "MSG_HEADER_TITLE=파이썬 패키지 설치를 시작합니다."
set "MSG_RECOMMENDED_VERSION=권장 Python 버전: 3.10.11"
set "MSG_REQUIRED_PACKAGES=필수 패키지: Pillow, UnityPy, xxhash"
set "MSG_DEFAULT_PYTHON_NOTICE=** 시스템에 설정된 기본 Python을 사용하여 설치를 진행합니다. **"
set "MSG_CHECKING_CONNECTION=인터넷 연결을 확인하고 있습니다..."
set "MSG_OFFLINE_MODE=[오프라인 모드] 인터넷에 연결되어 있지 않습니다."
set "MSG_OFFLINE_INSTALL=로컬 'packages' 폴더에서 설치를 진행합니다..."
set "MSG_ONLINE_MODE=[온라인 모드] 인터넷에 연결되었습니다."
set "MSG_ONLINE_INSTALL=온라인 저장소(PyPI)에서 패키지를 설치합니다..."
set "MSG_ERROR_HEADER=[오류] 패키지 설치 중 문제가 발생했습니다."
set "MSG_ERROR_CHECK_PYTHON=- Python이 설치되어 있고, 시스템의 '기본' Python으로 설정되었는지 확인해주세요."
set "MSG_ERROR_HOW_TO_CHECK=-(확인 방법: 터미널에서 'py --version' 또는 'python --version' 실행)"
set "MSG_ERROR_ADMIN=- 터미널을 관리자 권한으로 실행한 후 다시 시도해보세요."
set "MSG_SUCCESS_HEADER=[성공] 모든 필수 패키지가 성공적으로 설치되었습니다."
set "MSG_EXIT_PROMPT=창을 닫으려면 아무 키나 누르세요."
goto :main_install

:set_english
set "MSG_HEADER_TITLE=This script will install the required Python packages."
set "MSG_RECOMMENDED_VERSION=Recommended Python Version: 3.10.11"
set "MSG_REQUIRED_PACKAGES=Required Packages: Pillow, UnityPy, xxhash"
set "MSG_DEFAULT_PYTHON_NOTICE=** Installation will proceed using the system's default Python. **"
set "MSG_CHECKING_CONNECTION=Checking for internet connection..."
set "MSG_OFFLINE_MODE=[Offline Mode] No internet connection detected."
set "MSG_OFFLINE_INSTALL=Installing from the local 'packages' folder..."
set "MSG_ONLINE_MODE=[Online Mode] Internet connection successful."
set "MSG_ONLINE_INSTALL=Installing packages from the online repository (PyPI)..."
set "MSG_ERROR_HEADER=[ERROR] An error occurred during package installation."
set "MSG_ERROR_CHECK_PYTHON=- Please ensure Python is installed AND set as the system's default Python."
set "MSG_ERROR_HOW_TO_CHECK=-(How to check: Run 'py --version' or 'python --version' in your terminal)"
set "MSG_ERROR_ADMIN=- Try running this script as an administrator."
set "MSG_SUCCESS_HEADER=[SUCCESS] All required packages have been installed."
set "MSG_EXIT_PROMPT=Press any key to exit."
goto :main_install

:set_japanese
set "MSG_HEADER_TITLE=Pythonパッケージのインストールを開始します。"
set "MSG_RECOMMENDED_VERSION=推奨Pythonバージョン: 3.10.11"
set "MSG_REQUIRED_PACKAGES=必須パッケージ: Pillow, UnityPy, xxhash"
set "MSG_DEFAULT_PYTHON_NOTICE=** システムに設定されているデフォルトのPythonを使用してインストールを進めます。**"
set "MSG_CHECKING_CONNECTION=インターネット接続を確認しています..."
set "MSG_OFFLINE_MODE=[オフラインモード] インターネットに接続されていません。"
set "MSG_OFFLINE_INSTALL=ローカルの 'packages' フォルダからインストールします..."
set "MSG_ONLINE_MODE=[オンラインモード] インターネットに接続されています。"
set "MSG_ONLINE_INSTALL=オンラインリポジトリ(PyPI)からパッケージをインストールします..."
set "MSG_ERROR_HEADER=[エラー] パッケージのインストール中に問題が発生しました。"
set "MSG_ERROR_CHECK_PYTHON=- Python がインストールされ、システムの「デフォルト」Pythonとして設定されていることを確認してください。"
set "MSG_ERROR_HOW_TO_CHECK=-(確認方法: ターミナルで 'py --version' または 'python --version' を実行)"
set "MSG_ERROR_ADMIN=- このスクリプトを管理者として実行してみてください。"
set "MSG_SUCCESS_HEADER=[成功] 必要なすべてのパッケージが正常にインストールされました。"
set "MSG_EXIT_PROMPT=何かキーを押して終了してください。"
goto :main_install


rem ======================================================================
rem 메인 설치 로직 (Main Installation Logic)
rem ======================================================================
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
echo  %MSG_DEFAULT_PYTHON_NOTICE%
echo.

rem --- 인터넷 연결 확인 ---
echo.
echo  %MSG_CHECKING_CONNECTION%
echo.
ping -n 1 8.8.8.8 >nul

rem --- 설치 방법 분기 ---
if errorlevel 1 (
    goto :install_offline
) else (
    goto :install_online
)


:install_offline
rem --- 오프라인 설치 로직 ---
echo  %MSG_OFFLINE_MODE%
echo.
echo  %MSG_OFFLINE_INSTALL%
echo.
py -m pip install --no-index --find-links=./packages -r requirements.txt 2>nul
goto :check_result


:install_online
rem --- 온라인 설치 로직 ---
echo  %MSG_ONLINE_MODE%
echo.
echo  %MSG_ONLINE_INSTALL%
echo.
py -m pip install -r requirements.txt 2>nul
goto :check_result


:check_result
rem --- 최종 결과 확인 분기 ---
if errorlevel 1 goto :handle_error
goto :handle_success


:handle_success
rem --- 성공 메시지 출력 ---
echo.
echo ======================================================================
echo  %MSG_SUCCESS_HEADER%
echo ======================================================================
echo.
goto :end_script


:handle_error
rem --- 오류 메시지 출력 ---
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
rem --- 스크립트 종료 ---
echo.
echo  %MSG_EXIT_PROMPT%
pause >nul
exit