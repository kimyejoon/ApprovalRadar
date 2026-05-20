"""
ApprovalRadar 런처 — Tkinter GUI
PyInstaller 진입점: 이 파일이 exe의 entry point입니다.
"""

import sys
import os

# ── PyInstaller 번들 환경: sys.path 보정 ─────────────────────────────────────
if getattr(sys, 'frozen', False):
    _bundle_dir = sys._MEIPASS  # type: ignore[attr-defined]
    if _bundle_dir not in sys.path:
        sys.path.insert(0, _bundle_dir)

from app.launcher.gui import LauncherApp

def main() -> None:
    app = LauncherApp()
    app.mainloop()

if __name__ == "__main__":
    main()
