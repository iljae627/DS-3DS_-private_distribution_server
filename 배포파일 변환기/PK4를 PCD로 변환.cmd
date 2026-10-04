@echo off
chcp 65001 >nul
cd /d "%~dp0"
"%~dp0배포파일 변환기.exe" %*
pause
