from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any


_browser_target: ContextVar[dict[str, Any] | None] = ContextVar("deskpilot_browser_target", default=None)


def bind_browser_target(target: dict[str, Any] | None) -> Token:
    return _browser_target.set(target)


def reset_browser_target(token: Token) -> None:
    _browser_target.reset(token)


def current_browser_target() -> dict[str, Any] | None:
    return _browser_target.get()

