@echo off
REM ============================================================================
REM  ApprovalRadar - Windows Build Script
REM  Usage: build.bat (double-click or run in cmd)
REM  Requirements: Python 3.11+, Node.js 18+
REM ============================================================================
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ── Path Setup ───────────────────────────────────────────────────────────────
set "SCRIPT_DIR=%~dp0"
set "BE_DIR=%SCRIPT_DIR%ApprovalRadar-BE"
set "FE_DIR=%SCRIPT_DIR%ApprovalRadar-FE"
set "RELEASE_DIR=%SCRIPT_DIR%dist_release"

echo.
echo   +==========================================+
echo   ^|     ApprovalRadar -- Build Script        ^|
echo   ^|     Windows                              ^|
echo   +==========================================+
echo.

REM ── Prerequisites Check ──────────────────────────────────────────────────────
echo [STEP 0] Checking prerequisites...

where python >nul 2>&1 || (
    echo [ERROR] Python not found. Install from https://python.org
    rem pause & rem exit /b 1
)
where node >nul 2>&1 || (
    echo [ERROR] Node.js not found. Install from https://nodejs.org
    rem pause & rem exit /b 1
)
where npm >nul 2>&1 || (
    echo [ERROR] npm not found.
    rem pause & rem exit /b 1
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
for /f "tokens=*" %%v in ('node --version 2^>^&1') do set NODE_VER=%%v
echo [INFO]  %PY_VER% / Node.js %NODE_VER%
echo [OK]    Prerequisites satisfied
echo.

REM ── STEP 1: Frontend Build ───────────────────────────────────────────────────
echo ====  STEP 1 / 4 -- Frontend Build  ====
cd /d "%FE_DIR%"

echo [INFO]  Installing npm packages...
call npm install
if errorlevel 1 ( echo [ERROR] npm install failed. & exit /b 1 )

echo [INFO]  Building React app...
call npm run build
if errorlevel 1 ( echo [ERROR] npm run build failed. & exit /b 1 )

if not exist "%FE_DIR%\dist" (
    echo [ERROR] Frontend build failed: dist\ not found.
    rem pause & rem exit /b 1
)
echo [OK]    Frontend build complete
echo.

REM ── STEP 2: Copy FE dist to BE folder ───────────────────────────────────────
echo ====  STEP 2 / 4 -- Copy Build Files  ====
if exist "%BE_DIR%\dist" rmdir /s /q "%BE_DIR%\dist"
xcopy /E /I /Q "%FE_DIR%\dist" "%BE_DIR%\dist"
if errorlevel 1 ( echo [ERROR] File copy failed. & exit /b 1 )
echo [OK]    FE dist copied
echo.

REM ── STEP 3: Python venv & dependencies ──────────────────────────────────────
echo ====  STEP 3 / 4 -- Python Environment  ====
cd /d "%BE_DIR%"

if not exist "%BE_DIR%\venv" (
    echo [INFO]  Creating virtual environment...
    python -m venv venv
    if errorlevel 1 ( echo [ERROR] venv creation failed. & exit /b 1 )
)

call "%BE_DIR%\venv\Scripts\activate.bat"

echo [INFO]  Installing dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

REM Remove uvloop (not supported on Windows)
python -m pip uninstall -y uvloop >nul 2>&1

python -m pip install --quiet pyinstaller
echo [OK]    Python environment ready
echo.

REM ── STEP 4: PyInstaller Build ────────────────────────────────────────────────
echo ====  STEP 4 / 4 -- PyInstaller Build  ====
cd /d "%BE_DIR%"

echo [INFO]  Starting PyInstaller build... (may take several minutes)
pyinstaller ApprovalRadar.spec --clean --noconfirm
if errorlevel 1 ( echo [ERROR] PyInstaller build failed. & exit /b 1 )

if not exist "%BE_DIR%\dist\ApprovalRadar.exe" (
    echo [ERROR] Build failed: ApprovalRadar.exe not found.
    rem pause & rem exit /b 1
)
echo.

REM ── Package Release ──────────────────────────────────────────────────────────
echo ====  Release Package  ====

if not exist "%RELEASE_DIR%" mkdir "%RELEASE_DIR%"

REM Always overwrite the executable
copy /Y "%BE_DIR%\dist\ApprovalRadar.exe" "%RELEASE_DIR%\ApprovalRadar.exe" >nul

REM .env: preserve existing (user may have customized API keys)
if not exist "%RELEASE_DIR%\.env" (
    copy /Y "%BE_DIR%\.env" "%RELEASE_DIR%\.env" >nul
    echo [OK]    .env created ^(new^)
) else (
    echo [OK]    .env preserved ^(existing config kept^)
)

REM DB: preserve existing (contains crawled data), copy only if absent
if not exist "%RELEASE_DIR%\food_safety.db" (
    if exist "%BE_DIR%\food_safety.db" (
        copy /Y "%BE_DIR%\food_safety.db" "%RELEASE_DIR%\food_safety.db" >nul
        echo [OK]    DB file created ^(food_safety.db^)
    ) else (
        echo [WARN]  food_safety.db not found -- empty DB will be created on first launch.
    )
) else (
    echo [OK]    DB file preserved ^(existing food_safety.db kept^)
)

REM Create README (ASCII only to avoid encoding issues in .bat)
(
echo ===================================================
echo   ApprovalRadar -- How to Run ^(Windows^)
echo ===================================================
echo.
echo 1. Double-click 'ApprovalRadar.exe' in this folder.
echo 2. If Windows Defender SmartScreen appears:
echo    Click 'More info' -^> 'Run anyway'
echo 3. The launcher window will open and browser will launch automatically.
echo 4. To exit, click the [Exit] button in the launcher window.
echo.
echo ---------------------------------------------------
echo API Key: Edit .env file with Notepad
echo Database: food_safety.db ^(license change records^)
echo ---------------------------------------------------
echo.
echo WARNING: Deleting food_safety.db will erase all data.
echo          Back up the DB file before major operations.
) > "%RELEASE_DIR%\README.txt"

echo.
echo   +======================================================+
echo   ^|  Build Successful!                                   ^|
echo   ^|                                                      ^|
echo   ^|  Output: dist_release\                              ^|
echo   ^|  Files:                                             ^|
echo   ^|    - ApprovalRadar.exe   ^(executable^)              ^|
echo   ^|    - .env                ^(API key config^)          ^|
echo   ^|    - food_safety.db      ^(license data DB^)         ^|
echo   ^|    - README.txt          ^(instructions^)            ^|
echo   +======================================================+
echo.

call deactivate
rem pause
