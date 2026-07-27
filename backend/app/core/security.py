from __future__ import annotations

import re
from typing import Any


_SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)\b(password|access_token|refresh_token|api[_-]?key|cookie)\b\s*[:=]\s*[^\s,;]+"),
]


def contains_secret(value: Any) -> bool:
    text = value if isinstance(value, str) else repr(value)
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)


def redact_secrets(value: Any) -> Any:
    if isinstance(value, str):
        result = value
        for pattern in _SECRET_PATTERNS:
            result = pattern.sub("[REDACTED_SECRET]", result)
        return result
    if isinstance(value, dict):
        return {key: redact_secrets(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value
