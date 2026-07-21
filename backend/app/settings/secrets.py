from __future__ import annotations

import base64
import sys


def protect_secret(value: str) -> str:
    """Protect a local secret with the current Windows user's DPAPI key."""
    if not value:
        return ""
    raw = value.encode("utf-8")
    if sys.platform == "win32":
        import win32crypt

        encrypted = win32crypt.CryptProtectData(raw, "DeskPilot AI API Key", None, None, None, 0)
        return "dpapi:v1:" + base64.b64encode(encrypted).decode("ascii")
    # Non-Windows builds retain compatibility without pretending this is encryption.
    return "plain:v1:" + base64.b64encode(raw).decode("ascii")


def reveal_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        if value.startswith("dpapi:v1:"):
            if sys.platform != "win32":
                return None
            import win32crypt

            encrypted = base64.b64decode(value.removeprefix("dpapi:v1:"))
            return win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)[1].decode("utf-8")
        if value.startswith("plain:v1:"):
            return base64.b64decode(value.removeprefix("plain:v1:")).decode("utf-8")
        # Read legacy plaintext values once so existing development databases keep working.
        return value
    except (ValueError, UnicodeDecodeError):
        return None
