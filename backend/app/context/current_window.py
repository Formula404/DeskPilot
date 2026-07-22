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

    def describe(hwnd: int) -> dict:
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

    def is_overlay(info: dict) -> bool:
        process_name = str(info.get("process_name") or "").lower()
        title = str(info.get("title") or "").strip().lower()
        return "deskpilot" in process_name or title == "deskpilot"

    hwnd = win32gui.GetForegroundWindow()
    info = describe(hwnd)
    # The overlay is normally foreground when /context/snapshots is called. Walk
    # Z-order to bind the first real user window behind it instead of DeskPilot.
    if is_overlay(info):
        candidate = win32gui.GetWindow(hwnd, 2)  # GW_HWNDNEXT
        for _ in range(40):
            if not candidate:
                break
            if win32gui.IsWindowVisible(candidate) and win32gui.GetWindowText(candidate).strip():
                try:
                    candidate_info = describe(candidate)
                except (psutil.Error, OSError):
                    candidate_info = {}
                if candidate_info and not is_overlay(candidate_info):
                    info = candidate_info
                    break
            candidate = win32gui.GetWindow(candidate, 2)
    return info
