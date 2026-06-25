from __future__ import annotations


def click(x: int, y: int) -> None:
    import pyautogui

    pyautogui.click(x=x, y=y)


def type_text(text: str) -> None:
    import pyautogui

    pyautogui.write(text)
