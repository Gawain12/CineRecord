@echo off
REM CineRecord Build Script for Windows
REM Creates a standalone .exe file

echo CineRecord Build Script
echo ==========================

REM Check if PyInstaller is installed
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller
)

REM Clean previous builds
echo Cleaning previous builds...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul

REM Build the application
echo Building CineRecord...
pyinstaller CineRecord.spec --clean

echo.
echo Build complete!
echo.
echo Output: dist\CineRecord.exe
echo.
