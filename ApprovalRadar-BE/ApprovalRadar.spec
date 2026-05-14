# -*- mode: python ; coding: utf-8 -*-
"""
ApprovalRadar.spec — PyInstaller 빌드 스펙

사용법:
    pyinstaller ApprovalRadar.spec --clean

사전 조건:
    1. ApprovalRadar-FE/dist/ 빌드가 완료되어 있어야 함
       (build.sh / build.bat 스크립트가 자동으로 처리)
    2. venv가 활성화된 상태에서 실행
    3. pyinstaller 설치: pip install pyinstaller
"""

import sys
import os

# 현재 spec 파일 위치 (ApprovalRadar-BE/)
_HERE = os.path.dirname(os.path.abspath(SPEC))  # noqa: F821

# FE dist 경로 (BE 폴더 내 복사된 dist/)
_DIST_DIR = os.path.join(_HERE, 'dist')

# .env 파일
_ENV_FILE = os.path.join(_HERE, '.env')

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    [os.path.join(_HERE, 'launcher.py')],
    pathex=[_HERE],
    binaries=[],
    datas=[
        # FE 정적 빌드 (React dist → 번들 내 dist/ 폴더로)
        (_DIST_DIR, 'dist'),
        # .env (API 키 포함)
        (_ENV_FILE, '.'),
        # 백엔드 Python 모듈
        (os.path.join(_HERE, 'app'), 'app'),
        (os.path.join(_HERE, 'database.py'), '.'),
        (os.path.join(_HERE, 'main.py'), '.'),
        (os.path.join(_HERE, 'excel_export.py'), '.'),
        (os.path.join(_HERE, 'scraper.py'), '.'),
    ],
    hiddenimports=[
        # uvicorn 내부
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
        'uvicorn.logging',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.http.httptools_impl',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.protocols.websockets.websockets_impl',
        'uvicorn.protocols.websockets.wsproto_impl',
        'uvicorn.loops.asyncio',
        'uvicorn.loops.auto',
        # uvloop (Mac/Linux에서만 실제 로드됨)
        'uvicorn.loops.uvloop',
        # FastAPI / Starlette
        'fastapi',
        'fastapi.staticfiles',
        'fastapi.templating',
        'starlette.routing',
        'starlette.middleware.base',
        'starlette.staticfiles',
        'starlette.responses',
        # APScheduler
        'apscheduler',
        'apscheduler.schedulers.background',
        'apscheduler.triggers.interval',
        'apscheduler.triggers.cron',
        # httpx / asyncio
        'httpx',
        'httpx._transports.default',
        'anyio',
        'anyio._backends._asyncio',
        'anyio._backends._trio',
        # 기타
        'dotenv',
        'openpyxl',
        'pydantic',
        'pydantic_core',
        'h11',
        'httptools',
        'websockets',
        'tzlocal',
        'cachetools',
        # 백엔드 내부 모듈 (app/*)
        'app.api.router',
        'app.api.endpoints.approvals',
        'app.api.endpoints.health',
        'app.api.endpoints.stream',
        'app.api.endpoints.admin',
        'app.api.endpoints.settings',
        'app.core.config',
        'app.core.events',
        'app.core.logger',
        'app.core.port_finder',
        'app.core.scheduler',
        'app.clients.key_usage_repository',
        'app.repositories',
        'app.schemas',
        'app.services.diff_crawler',
        'app.services.industry_filler',
        'app.utils',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 개발/테스트 전용 모듈 제외
        'pytest',
        'pytest_asyncio',
        '_pytest',
        'IPython',
        'jupyter',
        'notebook',
        'matplotlib',
        'numpy',
        'pandas',
        'setuptools',
        'pip',
    ],
    noarchive=False,
    optimize=0,
)

# ── PYZ (Python 바이트코드 아카이브) ──────────────────────────────────────────
pyz = PYZ(a.pure)  # noqa: F821

# ── EXE 생성 ──────────────────────────────────────────────────────────────────
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ApprovalRadar',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,          # UPX 압축 (설치된 경우)
    upx_exclude=[],
    runtime_tmpdir=None,
    # windowed=True: 콘솔 창 없음 (런처 GUI 사용)
    # Mac에서는 콘솔 창 자체가 없으므로 무관
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # 아이콘 설정 (파일 존재 시 적용)
    # icon='assets/icon.ico',  # Windows
    # icon='assets/icon.icns', # Mac
)
