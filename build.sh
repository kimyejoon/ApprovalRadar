#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
#  ApprovalRadar — macOS/Linux 빌드 스크립트
#  사용법: bash build.sh
#  실행 전 요구사항: Python 3.11+, Node.js 18+
# ═══════════════════════════════════════════════════════════════════════════════

set -e  # 오류 발생 시 즉시 중단

# ── 색상 출력 유틸리티 ─────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'  # No Color

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
step()    { echo -e "\n${BLUE}━━━━━  $*  ━━━━━${NC}"; }

# ── 경로 설정 ──────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BE_DIR="$SCRIPT_DIR/ApprovalRadar-BE"
FE_DIR="$SCRIPT_DIR/ApprovalRadar-FE"
RELEASE_DIR="$SCRIPT_DIR/dist_release"

echo -e "${BLUE}"
echo "  ╔══════════════════════════════════════════╗"
echo "  ║     ApprovalRadar — Build Script         ║"
echo "  ║     macOS / Linux                        ║"
echo "  ╚══════════════════════════════════════════╝"
echo -e "${NC}"

# ── 사전 요구사항 체크 ─────────────────────────────────────────────────────────
step "사전 요구사항 확인"

command -v python3 &>/dev/null || error "Python 3가 설치되지 않았습니다. https://python.org 에서 설치해주세요."
command -v node   &>/dev/null || error "Node.js가 설치되지 않았습니다. https://nodejs.org 에서 설치해주세요."
command -v npm    &>/dev/null || error "npm이 설치되지 않았습니다."

PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
NODE_VER=$(node --version | sed 's/v//')
info "Python $PYTHON_VER / Node.js $NODE_VER"

# Python 최소 버전 체크 (3.11+)
python3 -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11+ 필요'" \
  || error "Python 3.11 이상이 필요합니다. 현재: $PYTHON_VER"

success "요구사항 충족"

# ── macOS libexpat 충돌 자동 해결 ─────────────────────────────────────────────
# Python 3.12+ Homebrew 빌드가 macOS 구버전 libexpat과 충돌하는 문제 방지
# (pyexpat, ensurepip, pip 모두 이 라이브러리에 의존)
EXPAT_LIB="/opt/homebrew/opt/expat/lib"
if [ -d "$EXPAT_LIB" ]; then
    export DYLD_LIBRARY_PATH="$EXPAT_LIB:${DYLD_LIBRARY_PATH}"
    info "Homebrew expat 경로 적용 → $EXPAT_LIB"
fi

# ── STEP 1: FE 빌드 ───────────────────────────────────────────────────────────
step "STEP 1 / 4 — 프론트엔드 빌드"

cd "$FE_DIR"
info "npm 패키지 설치 중..."
npm install --silent

info "React 앱 빌드 중... (production 모드)"
npm run build

FE_DIST="$FE_DIR/dist"
[ -d "$FE_DIST" ] || error "FE 빌드 실패: dist/ 폴더가 생성되지 않았습니다."
success "프론트엔드 빌드 완료 → $FE_DIST"

# ── STEP 2: FE dist를 BE 폴더로 복사 ─────────────────────────────────────────
step "STEP 2 / 4 — 빌드 파일 복사"

BE_DIST="$BE_DIR/dist"
rm -rf "$BE_DIST"
cp -r "$FE_DIST" "$BE_DIST"
success "FE dist 복사 완료 → $BE_DIST"

# ── STEP 3: Python 가상환경 & 의존성 설치 ─────────────────────────────────────
step "STEP 3 / 4 — Python 환경 구성"

cd "$BE_DIR"

VENV_DIR="$BE_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    info "가상환경 생성 중..."
    python3 -m venv "$VENV_DIR"
fi

PYTHON_BIN="$VENV_DIR/bin/python3"
PIP_BIN="$VENV_DIR/bin/pip"

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

info "의존성 설치 중..."
"$PIP_BIN" install --quiet --upgrade pip
"$PIP_BIN" install --quiet -r requirements.txt
"$PIP_BIN" install --quiet pyinstaller

success "Python 환경 구성 완료"

# ── STEP 4: PyInstaller 빌드 ──────────────────────────────────────────────────
step "STEP 4 / 4 — PyInstaller 빌드 (단일 exe)"

cd "$BE_DIR"
info "PyInstaller 빌드 시작... (수 분 소요될 수 있습니다)"
# iCloud Drive 환경에서 --clean 타이밍 문제 방지: 빌드 캐시만 수동 삭제
# (dist/는 STEP 2에서 복사한 FE 빌드가 있으므로 삭제 금지)
rm -rf "$BE_DIR/build" "$BE_DIR/dist_exe"
# FE dist/와 충돌 방지: PyInstaller 출력을 dist_exe/로 분리
"$VENV_DIR/bin/pyinstaller" ApprovalRadar.spec --noconfirm --distpath "$BE_DIR/dist_exe"

EXE_PATH="$BE_DIR/dist_exe/ApprovalRadar"
[ -f "$EXE_PATH" ] || error "PyInstaller 빌드 실패: 실행파일이 생성되지 않았습니다."

# ── 배포 패키지 정리 ──────────────────────────────────────────────────────────
step "배포 패키지 정리"

rm -rf "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"

# ── 실행 파일 복사 (.app 번들 우선, 없으면 단일 바이너리 폴백) ─────────────────
APP_BUNDLE="$BE_DIR/dist_exe/ApprovalRadar.app"
EXE_BIN="$BE_DIR/dist_exe/ApprovalRadar"

if [ -d "$APP_BUNDLE" ]; then
    info ".app 번들 감지 → dist_release/ApprovalRadar.app 로 복사 중..."
    cp -r "$APP_BUNDLE" "$RELEASE_DIR/ApprovalRadar.app"
    chmod -R +x "$RELEASE_DIR/ApprovalRadar.app"
    success ".app 번들 복사 완료 (더블클릭으로 실행 가능)"
elif [ -f "$EXE_BIN" ]; then
    cp "$EXE_BIN" "$RELEASE_DIR/ApprovalRadar"
    chmod +x "$RELEASE_DIR/ApprovalRadar"
    warn ".app 번들 없음 → 단일 바이너리로 배포 (터미널 실행 필요)"
else
    error "빌드 결과물 없음: ApprovalRadar.app / ApprovalRadar 모두 찾을 수 없습니다."
fi

# .env (API 키 — 유저 편집 가능)
cp "$BE_DIR/.env" "$RELEASE_DIR/.env"

# DB 파일 (미러링/운영 데이터 포함)
DB_FILE="$BE_DIR/food_safety.db"
if [ -f "$DB_FILE" ]; then
    cp "$DB_FILE" "$RELEASE_DIR/food_safety.db"
    DB_SIZE=$(du -sh "$DB_FILE" | cut -f1)
    success "DB 파일 포함 → food_safety.db ($DB_SIZE)"
else
    warn "food_safety.db 없음 → 앱 첫 실행 시 빈 DB 자동 생성됩니다."
fi

# 실행 안내 텍스트 (UTF-8 강제)
cat > "$RELEASE_DIR/실행방법.txt" << 'EOF'
═══════════════════════════════════════════════════
  ApprovalRadar — 실행 방법 (macOS)
═══════════════════════════════════════════════════

1. 이 폴더에서 'ApprovalRadar' 파일을 더블클릭합니다.
2. 처음 실행 시 macOS 보안 경고가 뜰 수 있습니다:
   시스템 환경설정 → 개인정보 보호 및 보안 → '확인 없이 열기' 클릭
   또는: 터미널에서 xattr -cr ./ApprovalRadar 실행 후 재시도
3. 런처 창이 뜨고, 브라우저가 자동으로 열립니다.
4. 종료 시 런처 창의 [종료] 버튼을 클릭합니다.

───────────────────────────────────────────────────
API 키 설정: .env 파일을 텍스트 편집기로 열어 수정
DB 파일:     food_safety.db (인허가 데이터 저장소)
───────────────────────────────────────────────────

⚠️  주의: food_safety.db 파일을 삭제하면 모든 데이터가 초기화됩니다.
          백업이 필요한 경우 DB 파일을 별도 위치에 복사하세요.
EOF

success "배포 패키지 생성 완료!"

echo -e "\n${GREEN}╔══════════════════════════════════════════════════════╗"
echo    "║  ✅  빌드 성공!                                      ║"
echo    "║                                                      ║"
echo -e "║  📦  배포 폴더: ${NC}dist_release/${GREEN}                        ║"
echo    "║  📂  포함 파일:                                      ║"
echo    "║       • ApprovalRadar.app  (macOS 앱 — 더블클릭)    ║"
echo    "║       • .env               (API 키 설정)             ║"
echo    "║       • food_safety.db     (인허가 데이터 DB)        ║"
echo    "║       • 실행방법.txt       (안내 문서)               ║"
echo    "╚══════════════════════════════════════════════════════╝"
echo -e "${NC}"

deactivate
