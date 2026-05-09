@echo off
setlocal

set ROOT=%~dp0..\..
set PYTHON=%ROOT%\.venv\Scripts\python.exe

if not exist "%PYTHON%" (
  echo Missing Python: %PYTHON%
  exit /b 1
)

"%PYTHON%" -m PyInstaller ^
  --noconfirm ^
  --onefile ^
  --windowed ^
  --name LabelHelper ^
  --distpath "%~dp0dist" ^
  --workpath "%~dp0build" ^
  --specpath "%~dp0build" ^
  "%~dp0recipe_db_tagger.py"

endlocal
