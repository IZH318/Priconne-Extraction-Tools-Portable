@echo off

TITLE Princess Connect! Re:Dive Original Resource Remover

echo.
echo. [ 주의 ] 원본 Resource 파일을 모두 삭제합니다.
echo.          삭제 된 파일은 휴지통을 거치지 않고 바로 삭제됩니다.
echo.
echo. 제거 대상은 다음과 같습니다.
echo. Assetbundles (*.unity3d)
echo. Audio (*.awb, *.acb)
echo. Video (*.usm)
echo.
echo. 원본 Resource 파일을 모두 삭제하려면 아무 키를 눌러 진행하십시오.
echo.
pause

echo.
echo.
echo.
echo. *.unity3d 파일을 모두 삭제합니다.
del /s *.unity3d
echo.

echo. *.awb 파일을 모두 삭제합니다.
del /s *.awb
echo.

echo. *.acb 파일을 모두 삭제합니다.
del /s *.acb
echo.

echo. *.usm 파일을 모두 삭제합니다.
del /s *.usm
echo.

echo.
echo.
echo. 원본 Resource 파일을 모두 삭제했습니다. 아무 키를 눌러 창을 종료하십시오 . . .
echo.

pause