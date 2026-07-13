from __future__ import annotations


def detect_intent(message: str) -> str:
    normalized = message.lower()
    table_keywords = ["表格", "excel", "xlsx"]
    export_keywords = ["导出", "保存", "提取", "抽取", "生成", "写入", "excel", "xlsx"]
    if any(
        keyword in normalized
        for keyword in ["接受提案", "同意提案", "批准提案", "应用提案", "拒绝提案", "驳回提案", "审核提案", "知识更新提案"]
    ):
        return "knowledge_review"
    if any(keyword in normalized for keyword in ["检查知识库", "知识库检查", "知识库健康", "知识索引", "断链"]):
        return "knowledge_maintenance"
    if any(
        keyword in normalized
        for keyword in ["加入知识库", "存入知识库", "归档当前页面", "归档当前网页", "收藏到知识库", "记住这篇", "导入文件到知识库", "导入知识库"]
    ):
        return "knowledge_ingest"
    if any(keyword in normalized for keyword in table_keywords) and any(
        keyword in normalized for keyword in export_keywords
    ):
        return "web_table_export"
    if any(
        keyword in normalized
        for keyword in ["在知识库", "查知识库", "查询知识库", "根据我的资料", "我收集过", "知识库里", "知识库中"]
    ):
        return "knowledge_query"
    if any(keyword in normalized for keyword in ["网页", "页面", "website", "page", "总结"]):
        return "web_page_summary"
    if any(keyword in normalized for keyword in ["打开", "启动"]):
        return "desktop_app_open"
    return "general_chat"
