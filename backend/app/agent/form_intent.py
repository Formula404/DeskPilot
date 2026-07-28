from __future__ import annotations


FORM_MEMORY_WORDS = ("记住", "保存", "记录", "收录")
FORM_FILL_WORDS = ("填", "填写", "自动填", "预览")


def is_form_memory_request(text: str) -> bool:
    normalized = text.strip().lower()
    return "表单" in normalized and any(word in normalized for word in FORM_MEMORY_WORDS)


def is_form_fill_request(text: str) -> bool:
    normalized = text.strip().lower()
    return "表单" in normalized and any(word in normalized for word in FORM_FILL_WORDS)
