from __future__ import annotations


def detect_intent(message: str) -> str:
    normalized = message.lower()
    table_keywords = ["表格", "excel", "xlsx"]
    export_keywords = ["导出", "保存", "提取", "抽取", "生成", "写入", "excel", "xlsx"]
    if any(keyword in normalized for keyword in table_keywords) and any(
        keyword in normalized for keyword in export_keywords
    ):
        return "web_table_export"
    if any(keyword in normalized for keyword in ["网页", "页面", "website", "page", "总结"]):
        return "web_page_summary"
    if any(keyword in normalized for keyword in ["打开", "启动"]):
        return "desktop_app_open"
    return "general_chat"
