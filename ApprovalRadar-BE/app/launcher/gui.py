import threading
import webbrowser
import queue
import tkinter as tk
from tkinter import scrolledtext
from app.launcher.config import COLORS, WINDOW_W, WINDOW_H, LOG_QUEUE
from app.launcher.server import (
    _setup_log_capture,
    _run_server,
    _wait_for_server,
    _shutdown_flag
)

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
        # 가로 고정 / 세로 자유
        self.resizable(False, True)
        self.minsize(WINDOW_W, WINDOW_H)  # 최소 크기 보장

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

        # 복사 기능
        self._log_area.bind('<Button-1>', lambda e: self._log_area.focus_set())
        self._log_area.bind('<Control-c>', self._copy_selection)
        self._log_area.bind('<Command-c>', self._copy_selection)
        self._log_area.bind('<Control-a>', self._select_all)
        self._log_area.bind('<Command-a>', self._select_all)
        self._log_area.bind('<B1-Motion>', self._on_log_drag)

        # 우클릭 컨텍스트 메뉴
        self._ctx_menu = tk.Menu(self, tearoff=0, bg=COLORS['surface2'],
                                  fg=COLORS['text'], activebackground=COLORS['accent_dim'])
        self._ctx_menu.add_command(label='전체 선택  (Cmd+A)', command=lambda: self._select_all(None))
        self._ctx_menu.add_command(label='복사       (Cmd+C)', command=lambda: self._copy_selection(None))
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label='로그 지우기', command=self._clear_log)
        self._log_area.bind('<Button-2>', self._show_ctx_menu)
        self._log_area.bind('<Button-3>', self._show_ctx_menu)

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
                
                t = threading.Thread(
                    target=_run_server, args=(port,), daemon=True, name="UvicornThread"
                )
                t.start()

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

    # ── 로그 복사 헬퍼 ────────────────────────────────────────────────────────
    def _copy_selection(self, event) -> str:
        try:
            selected = self._log_area.get(tk.SEL_FIRST, tk.SEL_LAST)
            self.clipboard_clear()
            self.clipboard_append(selected)
        except tk.TclError:
            pass
        return 'break'

    def _select_all(self, event) -> str:
        self._log_area.tag_add(tk.SEL, '1.0', tk.END)
        self._log_area.mark_set(tk.INSERT, '1.0')
        self._log_area.see(tk.INSERT)
        return 'break'

    def _show_ctx_menu(self, event) -> None:
        try:
            self._ctx_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._ctx_menu.grab_release()

    def _clear_log(self) -> None:
        self._log_area.config(state='normal')
        self._log_area.delete('1.0', tk.END)
        self._log_area.config(state='disabled')

    def _on_log_drag(self, event) -> None:
        h = self._log_area.winfo_height()
        edge = 24
        if event.y < edge:
            self._log_area.yview_scroll(-1, 'units')
        elif event.y > h - edge:
            self._log_area.yview_scroll(1, 'units')

    # ── 종료 처리 ─────────────────────────────────────────────────────────────
    def _on_close(self) -> None:
        self._append_log("🛑 서버를 종료합니다...")
        _shutdown_flag.set()
        self.after(800, self.destroy)
