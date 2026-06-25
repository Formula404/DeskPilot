from __future__ import annotations


def detect_intent(message: str) -> str:
    normalized = message.lower()
    if any(keyword in normalized for keyword in ["网页", "页面", "website", "page", "总结"]):
        return "web_page_summary"
    if any(keyword in normalized for keyword in ["表格", "excel", "xlsx"]):
        return "web_table_export"
    if any(keyword in normalized for keyword in ["打开", "启动"]):
        return "desktop_app_open"
    return "general_chat"
