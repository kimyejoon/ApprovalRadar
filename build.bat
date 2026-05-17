@echo off
REM ═══════════════════════════════════════════════════════════════════════════
REM  ApprovalRadar — Windows 빌드 스크립트
REM  사용법: build.bat (더블클릭 또는 cmd에서 실행)
REM  실행 전 요구사항: Python 3.11+, Node.js 18+
REM ═══════════════════════════════════════════════════════════════════════════
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ── 경로 설정 ───────────────────────────────────────────────────────────────
set "SCRIPT_DIR=%~dp0"
set "BE_DIR=%SCRIPT_DIR%ApprovalRadar-BE"
set "FE_DIR=%SCRIPT_DIR%ApprovalRadar-FE"
set "RELEASE_DIR=%SCRIPT_DIR%dist_release"

echo.
echo   ╔══════════════════════════════════════════╗
echo   ║     ApprovalRadar -- Build Script        ║
echo   ║     Windows                              ║
echo   ╚══════════════════════════════════════════╝
echo.

REM ── 사전 요구사항 체크 ──────────────────────────────────────────────────────
echo [STEP 0] 사전 요구사항 확인...

where python >nul 2>&1 || (
    echo [ERROR] Python이 설치되지 않았습니다. https://python.org 에서 설치해주세요.
    pause & exit /b 1
)
where node >nul 2>&1 || (
    echo [ERROR] Node.js가 설치되지 않았습니다. https://nodejs.org 에서 설치해주세요.
    pause & exit /b 1
)
where npm >nul 2>&1 || (
    echo [ERROR] npm이 설치되지 않았습니다.
    pause & exit /b 1
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
for /f "tokens=*" %%v in ('node --version 2^>^&1') do set NODE_VER=%%v
echo [INFO]  %PY_VER% / Node.js %NODE_VER%
echo [OK]    요구사항 충족
echo.

REM ── STEP 1: FE 빌드 ─────────────────────────────────────────────────────────
echo ━━━━━  STEP 1 / 4 -- 프론트엔드 빌드  ━━━━━
cd /d "%FE_DIR%"

echo [INFO]  npm 패키지 설치 중...
call npm install --silent
if errorlevel 1 ( echo [ERROR] npm install 실패. & pause & exit /b 1 )

echo [INFO]  React 앱 빌드 중...
call npm run build
if errorlevel 1 ( echo [ERROR] npm run build 실패. & pause & exit /b 1 )

if not exist "%FE_DIR%\dist" (
    echo [ERROR] FE 빌드 실패: dist\ 폴더가 없습니다.
    pause & exit /b 1
)
echo [OK]    프론트엔드 빌드 완료
echo.

REM ── STEP 2: FE dist를 BE 폴더로 복사 ───────────────────────────────────────
echo ━━━━━  STEP 2 / 4 -- 빌드 파일 복사  ━━━━━
if exist "%BE_DIR%\dist" rmdir /s /q "%BE_DIR%\dist"
xcopy /E /I /Q "%FE_DIR%\dist" "%BE_DIR%\dist"
if errorlevel 1 ( echo [ERROR] 파일 복사 실패. & pause & exit /b 1 )
echo [OK]    FE dist 복사 완료
echo.

REM ── STEP 3: Python 가상환경 & 의존성 설치 ───────────────────────────────────
echo ━━━━━  STEP 3 / 4 -- Python 환경 구성  ━━━━━
cd /d "%BE_DIR%"

if not exist "%BE_DIR%\venv" (
    echo [INFO]  가상환경 생성 중...
    python -m venv venv
    if errorlevel 1 ( echo [ERROR] venv 생성 실패. & pause & exit /b 1 )
)

call "%BE_DIR%\venv\Scripts\activate.bat"

echo [INFO]  의존성 설치 중...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

REM Windows에서는 uvloop 제거 (미지원)
python -m pip uninstall -y uvloop >nul 2>&1

python -m pip install --quiet pyinstaller
echo [OK]    Python 환경 구성 완료
echo.

REM ── STEP 4: PyInstaller 빌드 ────────────────────────────────────────────────
echo ━━━━━  STEP 4 / 4 -- PyInstaller 빌드  ━━━━━
cd /d "%BE_DIR%"

echo [INFO]  PyInstaller 빌드 시작... (수 분 소요될 수 있습니다)
pyinstaller ApprovalRadar.spec --clean --noconfirm
if errorlevel 1 ( echo [ERROR] PyInstaller 빌드 실패. & pause & exit /b 1 )

if not exist "%BE_DIR%\dist\ApprovalRadar.exe" (
    echo [ERROR] 빌드 실패: ApprovalRadar.exe가 생성되지 않았습니다.
    pause & exit /b 1
)
echo.

REM ── 배포 패키지 정리 ────────────────────────────────────────────────────────
echo ━━━━━  배포 패키지 정리  ━━━━━

if exist "%RELEASE_DIR%" rmdir /s /q "%RELEASE_DIR%"
mkdir "%RELEASE_DIR%"

copy /Y "%BE_DIR%\dist\ApprovalRadar.exe" "%RELEASE_DIR%\ApprovalRadar.exe" >nul

copy /Y "%BE_DIR%\.env" "%RELEASE_DIR%\.env" >nul

REM DB 파일 복사 (미러링/운영 데이터 포함)
if exist "%BE_DIR%\food_safety.db" (
    copy /Y "%BE_DIR%\food_safety.db" "%RELEASE_DIR%\food_safety.db" >nul
    echo [OK]    DB 파일 포함 ^(food_safety.db^)
) else (
    echo [WARN]  food_safety.db 없음 -- 앱 첫 실행 시 빈 DB 자동 생성됩니다.
)

REM 실행 안내 텍스트 (UTF-8)
(
echo ═══════════════════════════════════════════════════
echo   ApprovalRadar -- 실행 방법 ^(Windows^)
echo ═══════════════════════════════════════════════════
echo.
echo 1. 이 폴더에서 'ApprovalRadar.exe' 를 더블클릭합니다.
echo 2. Windows Defender 경고가 뜨면:
echo    '추가 정보' -^> '실행' 을 클릭합니다.
echo 3. 런처 창이 뜨고, 브라우저가 자동으로 열립니다.
echo 4. 종료 시 런처 창의 [종료] 버튼을 클릭합니다.
echo.
echo ───────────────────────────────────────────────────
echo API 키 설정: .env 파일을 메모장으로 열어 수정
echo DB 파일:     food_safety.db ^(인허가 데이터 저장소^)
echo ───────────────────────────────────────────────────
echo.
echo 주의: food_safety.db 파일을 삭제하면 모든 데이터가 초기화됩니다.
echo       백업이 필요한 경우 DB 파일을 별도 위치에 복사하세요.
) > "%RELEASE_DIR%\실행방법.txt"

echo.
echo   ╔══════════════════════════════════════════════════════╗
echo   ║  ✅  빌드 성공!                                      ║
echo   ║                                                      ║
echo   ║  📦  배포 폴더: dist_release\                        ║
echo   ║  📂  포함 파일:                                      ║
echo   ║       - ApprovalRadar.exe   ^(실행 파일^)             ║
echo   ║       - .env                ^(API 키 설정^)           ║
echo   ║       - food_safety.db      ^(인허가 데이터 DB^)      ║
echo   ║       - 실행방법.txt        ^(안내 문서^)             ║
echo   ╚══════════════════════════════════════════════════════╝
echo.

call deactivate
pause
