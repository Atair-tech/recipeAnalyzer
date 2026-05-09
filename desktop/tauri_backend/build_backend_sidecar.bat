@echo off
setlocal

cd /d "%~dp0"

if not exist "..\..\src-tauri\binaries" mkdir "..\..\src-tauri\binaries"
if exist "dist" rmdir /s /q "dist"

..\..\.venv\Scripts\python.exe build_sidecar.py

if errorlevel 1 exit /b %errorlevel%

copy /y "dist\recipe-backend-x86_64-pc-windows-msvc.exe" "..\..\src-tauri\binaries\recipe-backend-x86_64-pc-windows-msvc.exe" >nul
if errorlevel 1 exit /b %errorlevel%

echo Backend sidecar built at src-tauri\binaries\recipe-backend-x86_64-pc-windows-msvc.exe
