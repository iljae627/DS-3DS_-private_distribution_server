@echo off
setlocal
set "TOOL=%~dp0Gen5Converter.dll"

if not exist "%TOOL%" (
  echo ERROR: Gen5Converter.dll was not found.
  echo %TOOL%
  pause
  exit /b 1
)

if "%~1"=="" (
  dotnet "%TOOL%"
) else (
  dotnet "%TOOL%" "%~1"
)

if errorlevel 1 (
  echo.
  echo Conversion failed.
) else (
  echo.
  echo Conversion completed. Copy the PGF to the Gen 5 server gift folder.
)
pause
