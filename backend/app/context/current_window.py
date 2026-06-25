from __future__ import annotations

import sys


def get_foreground_window() -> dict:
    if sys.platform != "win32":
        return {
            "window_id": None,
            "process_name": None,
            "process_path": None,
            "title": None,
            "rect": None,
            "error": "Current window detection is only implemented for Windows.",
        }

    import win32gui
    import win32process
    import psutil

    hwnd = win32gui.GetForegroundWindow()
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    process = psutil.Process(pid)
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    return {
        "window_id": str(hwnd),
        "process_name": process.name(),
        "process_path": process.exe(),
        "title": win32gui.GetWindowText(hwnd),
        "rect": {
            "x": left,
            "y": top,
            "width": right - left,
            "height": bottom - top,
        },
    }
