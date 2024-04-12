@echo off

TITLE 00. Install required Python packages

echo.
echo. [ 안내 ] 필수 Python Package를 설치합니다.
echo.
echo.          이 과정은 가장 처음 한 번만 실행하면 됩니다.
echo.          (아래 Python Package를 미설치 또는 설치 후 삭제 한다면 제공 된 Python Script를 사용할 수 없습니다.)
echo.
echo.
echo.
echo. [ Package List ]

type requirements.txt

echo.
echo.
echo. 위 Package 설치를 진행하려면 아무 키나 누르십시오 . . .
echo.

pause
echo.
echo.
echo.

python -m pip install -r requirements.txt

echo.
echo.
echo.
echo. 필수 Python Package 설치가 완료되었습니다.
echo.

pause