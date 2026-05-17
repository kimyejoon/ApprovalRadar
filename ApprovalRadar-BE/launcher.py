"""
ApprovalRadar 런처 — Tkinter GUI
PyInstaller 진입점: 이 파일이 exe의 entry point입니다.

실행 흐름:
1. 포트 자동 탐지 (8000~8010)
2. uvicorn + FastAPI 백그라운드 스레드 시작
3. 서버 Ready 대기
4. 브라우저 자동 오픈
5. 런처 GUI (상태/로그/종료 버튼)
"""

import sys
import os
import threading
import time
import webbrowser
import tkinter as tk
from tkinter import scrolledtext, font as tkfont
import queue
import logging

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
    _bundle_dir = os.path.dirname(os.path.abspath(__file__))
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


# ── 로그 큐 핸들러 ────────────────────────────────────────────────────────────
class QueueLogHandler(logging.Handler):
    """Python logging → Tkinter 로그 뷰어로 전달"""
    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        LOG_QUEUE.put(msg)


def _setup_log_capture() -> None:
    """백엔드 로거를 큐 핸들러에 연결"""
    handler = QueueLogHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                                            datefmt="%H:%M:%S"))
    # 루트 로거 + uvicorn 로거
    for name in ("root", "uvicorn", "uvicorn.access", "uvicorn.error"):
        lg = logging.getLogger(name if name != "root" else "")
        if not any(isinstance(h, QueueLogHandler) for h in lg.handlers):
            lg.addHandler(handler)


# ── 서버 스레드 ───────────────────────────────────────────────────────────────
_server_thread: threading.Thread | None = None
_shutdown_flag = threading.Event()


def _run_server(port: int) -> None:
    """uvicorn 서버를 현재 스레드에서 실행 (blocking)"""
    # pyrefly: ignore [missing-import]
    import uvicorn
    from main import app

    loop = "asyncio"  # PyInstaller 번들에서 uvloop 동적 라이브러리 로딩 불안정 → asyncio 고정

    config = uvicorn.Config(
        app=app,
        host="127.0.0.1",
        port=port,
        loop=loop,          # Windows: asyncio, Mac/Linux: uvloop
        log_level="info",
    )
    server = uvicorn.Server(config)

    # 종료 플래그 감지 스레드
    def _watch_shutdown() -> None:
        _shutdown_flag.wait()
        server.should_exit = True

    threading.Thread(target=_watch_shutdown, daemon=True).start()
    server.run()


def _wait_for_server(port: int, timeout: float = 30.0) -> bool:
    """서버가 준비될 때까지 대기. 준비되면 True 반환."""
    import socket
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False


# ── 런처 GUI ─────────────────────────────────────────────────────────────────
class LauncherApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self._port: int = 0
        self._was_fallback: bool = False
        self._url: str = ""
        self._status: str = "starting"   # starting | running | error

        self._build_window()
        self._build_ui()
        self._start_backend()
        self._poll_logs()

    # ── 창 설정 ───────────────────────────────────────────────────────────────
    def _build_window(self) -> None:
        self.title("ApprovalRadar")
        self.configure(bg=COLORS['bg'])
        self.resizable(False, False)

        # 화면 중앙 배치
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - WINDOW_W) // 2
        y = (sh - WINDOW_H) // 2
        self.geometry(f"{WINDOW_W}x{WINDOW_H}+{x}+{y}")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI 구성 ───────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        pad = dict(padx=20, pady=8)

        # ── 헤더 ──────────────────────────────────────────────────────────────
        header = tk.Frame(self, bg=COLORS['surface'], bd=0)
        header.pack(fill='x')

        title_frame = tk.Frame(header, bg=COLORS['surface'])
        title_frame.pack(fill='x', padx=20, pady=16)

        tk.Label(
            title_frame, text="🛡️  ApprovalRadar",
            bg=COLORS['surface'], fg=COLORS['text'],
            font=("Helvetica", 18, "bold")
        ).pack(side='left')

        tk.Label(
            title_frame, text="인허가 변동 모니터링 시스템",
            bg=COLORS['surface'], fg=COLORS['text_muted'],
            font=("Helvetica", 10)
        ).pack(side='left', padx=(12, 0), pady=(6, 0))

        # ── 구분선 ────────────────────────────────────────────────────────────
        tk.Frame(self, bg=COLORS['border'], height=1).pack(fill='x')

        # ── 상태 영역 ─────────────────────────────────────────────────────────
        status_frame = tk.Frame(self, bg=COLORS['surface2'])
        status_frame.pack(fill='x', padx=16, pady=(12, 4))

        # 상태 표시
        row1 = tk.Frame(status_frame, bg=COLORS['surface2'])
        row1.pack(fill='x', padx=12, pady=(10, 4))

        tk.Label(row1, text="상태", bg=COLORS['surface2'],
                 fg=COLORS['text_muted'], font=("Helvetica", 9), width=6,
                 anchor='w').pack(side='left')

        self._status_dot = tk.Label(row1, text="●", bg=COLORS['surface2'],
                                     fg=COLORS['warn'], font=("Helvetica", 12))
        self._status_dot.pack(side='left', padx=(4, 6))

        self._status_label = tk.Label(row1, text="시작 중...",
                                       bg=COLORS['surface2'], fg=COLORS['warn'],
                                       font=("Helvetica", 11, "bold"))
        self._status_label.pack(side='left')

        # 주소 표시
        row2 = tk.Frame(status_frame, bg=COLORS['surface2'])
        row2.pack(fill='x', padx=12, pady=(2, 4))

        tk.Label(row2, text="주소", bg=COLORS['surface2'],
                 fg=COLORS['text_muted'], font=("Helvetica", 9), width=6,
                 anchor='w').pack(side='left')

        self._url_label = tk.Label(row2, text="—", bg=COLORS['surface2'],
                                    fg=COLORS['text_muted'],
                                    font=("Helvetica", 11), cursor="hand2")
        self._url_label.pack(side='left', padx=(4, 0))
        self._url_label.bind("<Button-1>", lambda _: self._open_browser())

        # 포트 변경 경고
        self._warn_frame = tk.Frame(status_frame, bg=COLORS['surface2'])
        self._warn_frame.pack(fill='x', padx=12, pady=(0, 8))
        self._warn_label = tk.Label(self._warn_frame, text="",
                                     bg=COLORS['surface2'], fg=COLORS['warn'],
                                     font=("Helvetica", 9), anchor='w')
        self._warn_label.pack(side='left')

        # ── 버튼 영역 ─────────────────────────────────────────────────────────
        btn_frame = tk.Frame(self, bg=COLORS['bg'])
        btn_frame.pack(fill='x', padx=16, pady=8)

        self._browser_btn = tk.Button(
            btn_frame, text="🌐  브라우저 열기",
            command=self._open_browser,
            bg=COLORS['accent_dim'], fg=COLORS['accent'],
            activebackground=COLORS['btn_hover'], activeforeground='white',
            font=("Helvetica", 11, "bold"),
            bd=0, padx=20, pady=8, cursor="hand2",
            state='disabled',
            relief='flat',
        )
        self._browser_btn.pack(side='left', padx=(0, 8))

        self._close_btn = tk.Button(
            btn_frame, text="✕  종료",
            command=self._on_close,
            bg=COLORS['surface2'], fg=COLORS['text_muted'],
            activebackground=COLORS['error'], activeforeground='white',
            font=("Helvetica", 11),
            bd=0, padx=20, pady=8, cursor="hand2",
            relief='flat',
        )
        self._close_btn.pack(side='left')

        # ── 로그 뷰어 ─────────────────────────────────────────────────────────
        tk.Frame(self, bg=COLORS['border'], height=1).pack(fill='x', pady=(4, 0))

        log_header = tk.Frame(self, bg=COLORS['bg'])
        log_header.pack(fill='x', padx=16, pady=(6, 2))
        tk.Label(log_header, text="로그", bg=COLORS['bg'],
                 fg=COLORS['text_muted'], font=("Helvetica", 9, "bold")).pack(side='left')

        self._log_area = scrolledtext.ScrolledText(
            self,
            bg=COLORS['surface'], fg='#94a3b8',
            font=("Courier", 9),
            bd=0, padx=8, pady=6,
            state='disabled',
            height=10,
            wrap='word',
        )
        self._log_area.pack(fill='both', expand=True, padx=16, pady=(0, 12))

        # 로그 색상 태그
        self._log_area.tag_config('ERROR', foreground=COLORS['error'])
        self._log_area.tag_config('WARNING', foreground=COLORS['warn'])
        self._log_area.tag_config('INFO', foreground='#94a3b8')

    # ── 백엔드 시작 ───────────────────────────────────────────────────────────
    def _start_backend(self) -> None:
        """별도 스레드에서 포트 탐지 → 서버 시작 → GUI 상태 업데이트"""
        def _worker() -> None:
            try:
                from app.core.port_finder import find_available_port
                port, was_fallback = find_available_port(8000, 8010)
                self._port = port
                self._was_fallback = was_fallback
                self._url = f"http://localhost:{port}"

                # 포트 변경 경고 표시
                if was_fallback:
                    self.after(0, self._show_port_warning, port)

                # 주소 업데이트
                self.after(0, self._update_url_label, self._url)

                # 서버 스레드 시작
                _setup_log_capture()
                global _server_thread
                _server_thread = threading.Thread(
                    target=_run_server, args=(port,), daemon=True, name="UvicornThread"
                )
                _server_thread.start()

                # 서버 Ready 대기
                ready = _wait_for_server(port, timeout=30.0)
                if ready:
                    self.after(0, self._set_running)
                    # 브라우저 자동 오픈 (1초 후)
                    self.after(1200, lambda: webbrowser.open(self._url))
                else:
                    self.after(0, self._set_error, "서버가 시작되지 않았습니다.")

            except RuntimeError as e:
                self.after(0, self._set_error, str(e))
            except Exception as e:
                self.after(0, self._set_error, f"오류: {e}")

        threading.Thread(target=_worker, daemon=True, name="LauncherWorker").start()

    # ── 상태 업데이트 헬퍼 ────────────────────────────────────────────────────
    def _update_url_label(self, url: str) -> None:
        self._url_label.config(text=url, fg=COLORS['text'])

    def _show_port_warning(self, port: int) -> None:
        self._warn_label.config(
            text=f"⚠  포트 8000이 사용 중이어서 {port}번 포트로 변경되었습니다."
        )

    def _set_running(self) -> None:
        self._status_dot.config(fg=COLORS['accent'])
        self._status_label.config(text="실행 중", fg=COLORS['accent'])
        self._browser_btn.config(state='normal')
        self._append_log(f"✅ 서버 준비 완료 → {self._url}")

    def _set_error(self, msg: str) -> None:
        self._status_dot.config(fg=COLORS['error'])
        self._status_label.config(text="오류 발생", fg=COLORS['error'])
        self._warn_label.config(text=msg, fg=COLORS['error'])
        self._append_log(f"❌ {msg}")

    # ── 로그 폴링 ─────────────────────────────────────────────────────────────
    def _poll_logs(self) -> None:
        """메인 루프에서 100ms마다 로그 큐를 소비하여 텍스트 위젯에 추가"""
        try:
            while True:
                msg = LOG_QUEUE.get_nowait()
                self._append_log(msg)
        except queue.Empty:
            pass
        self.after(100, self._poll_logs)

    def _append_log(self, msg: str) -> None:
        self._log_area.config(state='normal')
        # 로그 레벨에 따른 색상 태그
        tag = 'INFO'
        if '[ERROR]' in msg or 'ERROR' in msg:
            tag = 'ERROR'
        elif '[WARNING]' in msg or 'WARN' in msg:
            tag = 'WARNING'
        self._log_area.insert('end', msg + '\n', tag)
        self._log_area.see('end')
        self._log_area.config(state='disabled')

    # ── 브라우저 열기 ─────────────────────────────────────────────────────────
    def _open_browser(self) -> None:
        if self._url:
            webbrowser.open(self._url)

    # ── 종료 처리 ─────────────────────────────────────────────────────────────
    def _on_close(self) -> None:
        self._append_log("🛑 서버를 종료합니다...")
        _shutdown_flag.set()
        self.after(800, self.destroy)


# ── 진입점 ────────────────────────────────────────────────────────────────────
def main() -> None:
    app = LauncherApp()
    app.mainloop()


if __name__ == "__main__":
    main()
