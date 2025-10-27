@echo off
REM ================================
REM Build script for Storybook Mod Manager
REM Requires: Python + PyInstaller installed
REM ================================

REM Clean old build/dist folders
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul

REM Path to your main entry point
set MAIN_SCRIPT=Storybook_Mod_Manager.py

REM Path to your icon file (required, resolved relative to this script)
set ICON_FILE=%~dp0Storybook_Icon.ico

REM Name of the final exe
set APP_NAME=Storybook Mod Manager

echo Building %APP_NAME% with embedded UI resources and icon...

REM Check required files
if not exist "UI" (
    echo ERROR: UI folder not found! Make sure UI folder is in the same directory as this script.
    pause
    exit /b 1
)

if not exist "%ICON_FILE%" (
    echo ERROR: Icon file "%ICON_FILE%" not found! This build requires an icon.
    pause
    exit /b 1
)

if not exist "extensions.txt" (
    echo ERROR: extensions.txt not found! This build requires extensions.txt.
    pause
    exit /b 1
)

echo.
echo [████████████████████████████████████████] Processing...
echo.

pyinstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --icon="%ICON_FILE%" ^
    --name "%APP_NAME%" ^
    --add-data "UI;UI" ^
    --add-data "Storybook_Icon.ico;." ^
    --exclude-module _tkinter ^
    --exclude-module tkinter ^
    --exclude-module matplotlib ^
    --exclude-module numpy ^
    --exclude-module pandas ^
    --exclude-module PIL ^
    --exclude-module Pillow ^
    --exclude-module scipy ^
    --exclude-module sklearn ^
    --exclude-module tensorflow ^
    --exclude-module torch ^
    --exclude-module cv2 ^
    --exclude-module IPython ^
    --exclude-module jupyter ^
    --exclude-module pytest ^
    --exclude-module setuptools ^
    --exclude-module wheel ^
    --exclude-module pip ^
    --exclude-module multiprocessing ^
    --exclude-module concurrent ^
    --exclude-module asyncio ^
    --exclude-module unittest ^
    --exclude-module doctest ^
    --exclude-module sqlite3 ^
    --exclude-module dbm ^
    --exclude-module bz2 ^
    --exclude-module lzma ^
    --exclude-module gzip ^
    --exclude-module tarfile ^
    --exclude-module wave ^
    --exclude-module audioop ^
    --exclude-module imaplib ^
    --exclude-module nntplib ^
    --exclude-module poplib ^
    --exclude-module smtplib ^
    --exclude-module telnetlib ^
    --exclude-module uuid ^
    --exclude-module statistics ^
    --exclude-module fractions ^
    --exclude-module decimal ^
    --exclude-module cmath ^
    --exclude-module logging.config ^
    --exclude-module logging.handlers ^
    --upx-dir="C:\Users\Kyo\Downloads\upx-5.0.2-win64" ^
    "%MAIN_SCRIPT%"

echo.
echo Build complete! 
echo.
echo Your portable %APP_NAME%.exe is in the "dist" folder.
echo.
echo WHAT'S INCLUDED IN THE EXE:
echo   - Minimal Python runtime and PyQt5 only
echo   - UI folder (icons and themes)
echo   - extensions.txt
echo   - Storybook Icon.ico
echo.
echo WHAT STAYS EXTERNAL (to share with friends):
echo   1. The %APP_NAME%.exe file from dist folder
echo   2. Mod folders (BlackKnight, SecretRings, etc.)
echo   3. Temp_File folder (backup archive)
echo   4. Any settings.json file
echo.
echo Your friend just needs to put the exe in the same folder as the mod folders!
pause
