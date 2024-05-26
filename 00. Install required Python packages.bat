@echo off

TITLE 00. Install required Python packages (Off-line)

echo.
echo. [ 안내 ] 필수 Python Package를 설치합니다.
echo.
echo.          이 과정은 가장 처음 한 번만 실행하면 됩니다.
echo.          (아래 Python Package를 미설치 또는 설치 후 삭제 한다면 제공 된 Python Script를 사용할 수 없습니다.)
echo.
echo.
echo.

echo. [ Package List ]
echo. requests-futures==1.0.0
echo. UnityPy==1.9.28
echo. tqdm==4.66.2

echo.
echo.
echo.
echo. 필수 Python Package를 모두 설치하려면 아무 키나 누르십시오 . . .

set /p "=" < nul
pause > nul

for /r %%x in (*.whl) do (
    echo.
    echo.
    echo.
    echo. [ Install ]
    echo. %%x...
    python -m pip install "%%x"
)

echo.
echo.
echo.
echo. 필수 Python Package 설치가 완료되었습니다. 아무 키를 눌러 창을 종료하십시오 . . .

set /p "=" < nul
pause > nul