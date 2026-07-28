from __future__ import annotations

from backend.app.browser.bridge import browser_bridge
from backend.app.context.runtime_binding import current_browser_target
from backend.app.personal_info.service import create_form_session, mark_form_session_filled, remember_form
from backend.app.schemas.common import ToolResult
from backend.app.tools.base import ToolDefinition


def _session_reference(plan: dict) -> dict:
    return {"session_id": plan["session_id"], "summary": plan["summary"],
            "review_required": any(plan["summary"].get(name, 0) for name in
                                   ("choose", "confirm", "existing", "missing")),
            "submitted": False}


async def _remember(_: dict) -> ToolResult:
    page = await browser_bridge.inspect_form(target=current_browser_target())
    result = remember_form(page)
    safe_result = {key: result[key] for key in (
        "template_id", "learned_count", "recognized_count", "saved_count",
        "created_count", "merged_count", "skipped_count",
    )}
    safe_result["record_count"] = len(result["records"])
    return ToolResult(ok=True, data=safe_result,
                      message=(f"已识别 {result['recognized_count']} 个已填写控件；已写入个人信息库 "
                               f"{result['saved_count']} 个唯一字段（新增 {result['created_count']} 个，"
                               f"合并或更新 {result['merged_count']} 个），包含 {len(result['records'])} 条关联经历；"
                               "密码、验证码和文件字段不会保存。"))


async def _fill(payload: dict) -> ToolResult:
    page = await browser_bridge.inspect_form(target=current_browser_target())
    plan = create_form_session(page)
    if payload.get("preview_only"):
        return ToolResult(ok=True, data={"form_session": _session_reference(plan), "preview_only": True, "submitted": False},
                          message=(f"已生成填写预览：{plan['summary']['ready']} 项可直接填，"
                                   f"{plan['summary']['choose']} 项需选资料，{plan['summary']['confirm']} 项需确认，"
                                   f"{plan['summary']['missing']} 项缺少资料。"))
    assignments = plan["auto_assignments"]
    if not assignments:
        return ToolResult(ok=True, data={"form_session": _session_reference(plan), "filled_count": 0, "submitted": False},
                          message="已识别表单，没有可直接安全填写的字段；请在填写预览中处理候选、确认和缺失项。")
    strict_target = {"tab": page.get("tab_id"), "url": page.get("url"),
                     "document_id": page.get("document_id"), "strict_document": True}
    result = await browser_bridge.fill_form(assignments, target=strict_target)
    updated = mark_form_session_filled(plan["session_id"], list(result.get("filled") or [])) or plan
    pending = sum(updated["summary"].get(name, 0) for name in ("choose", "confirm", "existing", "missing"))
    safe_fill_result = {"filled_count": int(result.get("filled_count") or 0),
                        "skipped_count": len(result.get("skipped") or []), "submitted": False}
    return ToolResult(ok=True, data={"form_session": _session_reference(updated), **safe_fill_result},
                      message=(f"已安全填写 {result.get('filled_count', 0)} 项，未提交表单；"
                               f"另有 {pending} 项需要选择、确认或补充。"))


remember_current_form = ToolDefinition(
    name="browser.remember_current_form",
    description="识别当前网页表单，将用户已填写的非敏感字段按语义分类保存到可编辑个人信息库，并记住表单结构。用于‘记住这个表单中所填的内容’、‘记录表单信息’等明确请求。绝不读取密码、验证码或文件字段。",
    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    output_schema={"type": "object", "additionalProperties": True},
    risk_level="medium", required_permissions=["browser_context:read", "personal_info:write"],
    side_effects=["stores:personal_info", "stores:form_template"],
    examples=["记住这个表单中所填的内容"], handler=_remember,
)

fill_current_form = ToolDefinition(
    name="browser.fill_current_form",
    description="识别当前网页表单，根据字段标签、上下文和用户确认记忆匹配个人资料。仅自动填写网页为空且唯一高置信的普通文本字段；多条经历、选择控件、敏感项、长文本及已有内容返回本地确认会话。只填值，绝不点击提交；可仅返回预览。",
    input_schema={"type": "object", "properties": {"preview_only": {"type": "boolean", "default": False}}, "additionalProperties": False},
    output_schema={"type": "object", "additionalProperties": True},
    risk_level="medium", required_permissions=["browser_context:read", "browser_context:write", "personal_info:read"],
    side_effects=["changes:current_page_form_values", "never:submit_form"],
    examples=["帮我填页面的表单", "先预览能填写哪些字段"], handler=_fill,
)
