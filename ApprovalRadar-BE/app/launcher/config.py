import sys
import os
import queue

# ── PyInstaller 번들 환경: sys.path 보정 ─────────────────────────────────────
if getattr(sys, 'frozen', False):
    # exe가 압축 해제되는 임시 폴더를 Python 모듈 경로에 추가
    _bundle_dir = sys._MEIPASS  # type: ignore[attr-defined]
    if _bundle_dir not in sys.path:
        sys.path.insert(0, _bundle_dir)
    # .env 파일: macOS .app 번들이면 .app 옆 폴더, 아니면 exe 옆
    _exe_dir = os.path.dirname(sys.executable)
    if (os.path.basename(_exe_dir) == 'MacOS'
            and os.path.basename(os.path.dirname(_exe_dir)) == 'Contents'):
        _deploy_dir = os.path.abspath(os.path.join(_exe_dir, '..', '..', '..'))
    else:
        _deploy_dir = _exe_dir
    _env_file = os.path.join(_deploy_dir, '.env')
else:
    _bundle_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _env_file = os.path.join(_bundle_dir, '.env')

# .env 로드 (python-dotenv)
try:
    from dotenv import load_dotenv
    load_dotenv(_env_file)
except ImportError:
    pass

# ── 디자인 상수 ───────────────────────────────────────────────────────────────
COLORS = {
    'bg':          '#0f1117',
    'surface':     '#1a1d27',
    'surface2':    '#22263a',
    'border':      '#2e3350',
    'accent':      '#4ade80',   # 에메랄드 그린
    'accent_dim':  '#166534',
    'warn':        '#fbbf24',   # 노란색
    'error':       '#f87171',   # 빨간색
    'text':        '#e2e8f0',
    'text_muted':  '#64748b',
    'btn_hover':   '#22c55e',
}

WINDOW_W = 560
WINDOW_H = 480
LOG_QUEUE: queue.Queue = queue.Queue()
