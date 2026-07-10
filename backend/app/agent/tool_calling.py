from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from openai import AsyncOpenAI

from backend.app.core.config import get_settings
from backend.app.db.repository import add_task_step
from backend.app.schemas.common import ToolResult
from backend.app.tools.registry import tool_registry

logger = logging.getLogger(__name__)

WEB_PAGE_SUMMARY_TOOLS = [
    "browser.collect_current_page",
    "file.write_markdown",
]

WEB_TABLE_EXPORT_TOOLS = [
    "browser.export_table_to_xlsx",
    "browser.export_structured_blocks_to_xlsx",
]


class ToolCallingError(RuntimeError):
    pass


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _parse_arguments(raw_arguments: str) -> dict[str, Any]:
    if not raw_arguments:
        return {}
    parsed = json.loads(raw_arguments)
    if not isinstance(parsed, dict):
        raise ToolCallingError("工具参数必须是 JSON object。")
    return parsed


def _compact_data(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    compacted = dict(data)
    visible_text = compacted.get("visible_text")
    if isinstance(visible_text, str) and len(visible_text) > 12000:
        compacted["visible_text"] = visible_text[:12000] + "\n\n[内容已截断]"
    dom_summary = compacted.get("dom_summary")
    if isinstance(dom_summary, list) and len(dom_summary) > 50:
        compacted["dom_summary"] = dom_summary[:50]
        compacted["dom_summary_truncated"] = True
    return compacted


def _observation_for_model(result: ToolResult) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "message": result.message,
        "data": _compact_data(result.data),
        "artifacts": [artifact.model_dump() for artifact in result.artifacts],
        "error": result.error.model_dump() if result.error else None,
    }


def _summarize_failure_observations(observations: list[dict[str, Any]]) -> str:
    failures: list[str] = []
    for item in observations:
        observation = item.get("observation") or {}
        if observation.get("ok"):
            continue
        message = observation.get("message")
        error = observation.get("error") or {}
        code = error.get("code")
        tool = item.get("tool")
        if message:
            failures.append(f"{tool}: {code or 'ERROR'} - {message}")
    if not failures:
        return "没有可用的具体工具错误。"
    return "；".join(failures[-3:])


def _tool_error_observation(message: str, code: str = "TOOL_CALL_REJECTED") -> dict[str, Any]:
    return {
        "ok": False,
        "message": message,
        "data": None,
        "artifacts": [],
        "error": {"code": code, "detail": {}},
    }


def _assistant_tool_calls(message: Any) -> list[dict[str, Any]]:
    return [
        {
            "id": tool_call.id,
            "type": tool_call.type,
            "function": {
                "name": tool_call.function.name,
                "arguments": tool_call.function.arguments,
            },
        }
        for tool_call in message.tool_calls or []
    ]


def _record_task_step(
    *,
    task_id: str,
    step_index: int,
    step_type: str,
    name: str,
    status: str,
    input_data: Any = None,
    output_data: Any = None,
) -> dict[str, Any]:
    step = {
        "step_index": step_index,
        "type": step_type,
        "name": name,
        "status": status,
        "input": input_data,
        "output": output_data,
    }
    try:
        add_task_step(
            task_id,
            step_index=step_index,
            step_type=step_type,
            name=name,
            status=status,
            input_data=input_data,
            output_data=output_data,
        )
    except Exception:
        logger.exception("Failed to record task step")
    return step



async def _run_tool_agent(
    *,
    task_id: str,
    user_input: str,
    allowed_tools: list[str],
    system_prompt: str,
    no_tool_fallback: str,
    max_steps: int,
    before_tool_call: Callable[[str, dict[str, Any]], None] | None = None,
    after_tool_result: Callable[[str, ToolResult, dict[str, Any]], dict[str, Any]] | None = None,
    on_step_recorded: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    start_step_index: int = 1,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.openai_api_key:
        raise ToolCallingError("未配置 OPENAI_API_KEY，无法运行 tool calling Agent。")

    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or "https://api.openai.com/v1",
    )
    tools = tool_registry.openai_tools(allowed_tools)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},
    ]
    artifacts: list[dict[str, str]] = []
    observations: list[dict[str, Any]] = []
    last_step_index = start_step_index

    for _ in range(max_steps):
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        message = response.choices[0].message
        tool_calls = message.tool_calls or []

        if not tool_calls:
            final_response = message.content or ""
            if artifacts:
                last_step_index = start_step_index + len(observations) + 1
                step = _record_task_step(
                    task_id=task_id,
                    step_index=last_step_index,
                    step_type="agent",
                    name="tool_calling_final",
                    status="completed",
                    output_data={"final_response": final_response, "artifacts": artifacts},
                )
                if on_step_recorded:
                    await on_step_recorded(step)
                return {
                    "final_response": final_response,
                    "artifacts": artifacts,
                    "observations": observations,
                    "step_count": last_step_index,
                }

            messages.append({"role": "user", "content": no_tool_fallback})
            continue

        messages.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": _assistant_tool_calls(message),
            }
        )

        for tool_call in tool_calls:
            openai_name = tool_call.function.name
            try:
                tool = tool_registry.get_by_openai_name(openai_name)
                if tool.name not in allowed_tools:
                    raise ToolCallingError(f"当前任务不允许调用工具：{tool.name}")
                arguments = _parse_arguments(tool_call.function.arguments)
                if before_tool_call:
                    before_tool_call(tool.name, arguments)
                result = await tool_registry.call(tool.name, arguments)
                observation = _observation_for_model(result)
                if after_tool_result:
                    observation = after_tool_result(tool.name, result, observation)
                if result.artifacts:
                    artifacts.extend(artifact.model_dump() for artifact in result.artifacts)
            except Exception as exc:
                arguments = {"raw_arguments": tool_call.function.arguments}
                observation = _tool_error_observation(str(exc))

            observations.append({"tool": openai_name, "observation": observation})
            last_step_index = start_step_index + len(observations)
            step = _record_task_step(
                task_id=task_id,
                step_index=last_step_index,
                step_type="tool",
                name=openai_name,
                status="completed" if observation["ok"] else "failed",
                input_data={"arguments": arguments, "tool_call_id": tool_call.id},
                output_data=observation,
            )
            if on_step_recorded:
                await on_step_recorded(step)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": _json_dumps(observation),
                }
            )

    raise ToolCallingError(
        "Tool calling Agent 超过最大步数仍未完成任务。最近工具错误："
        + _summarize_failure_observations(observations)
    )


async def run_web_page_summary_tool_agent(
    *,
    task_id: str,
    user_input: str,
    max_steps: int = 5,
    on_step_recorded: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    start_step_index: int = 1,
) -> dict[str, Any]:
    has_page_context = False
    page_context_failed = False

    def before_tool_call(tool_name: str, _: dict[str, Any]) -> None:
        if tool_name != "file.write_markdown" or has_page_context:
            return
        if page_context_failed:
            raise ToolCallingError("已尝试采集当前网页但失败，请先解决网页采集错误，不能继续写入 Markdown。")
        raise ToolCallingError("必须先调用 browser_collect_current_page 获取当前网页内容。")

    def after_tool_result(tool_name: str, result: ToolResult, observation: dict[str, Any]) -> dict[str, Any]:
        nonlocal has_page_context, page_context_failed
        if tool_name != "browser.collect_current_page":
            return observation
        if not result.ok:
            page_context_failed = True
            return observation
        text = ((result.data or {}).get("visible_text") or "").strip()
        if not text:
            page_context_failed = True
            return _tool_error_observation("当前网页没有可总结的可见文本。", code="EMPTY_PAGE_TEXT")
        has_page_context = True
        return observation

    return await _run_tool_agent(
        task_id=task_id,
        user_input=user_input,
        allowed_tools=WEB_PAGE_SUMMARY_TOOLS,
        system_prompt=(
            "你是 DeskPilot 的网页总结 Agent。"
            "你必须通过工具完成任务，而不是假设网页内容。"
            "第一步调用 browser_collect_current_page 获取当前网页。"
            "如果网页 visible_text 为空，必须停止并说明当前网页没有可总结的可见文本，不能虚构内容。"
            "然后根据网页文本写出中文 Markdown 总结。"
            "调用 file_write_markdown 时，title 参数必须优先使用网页 title，content 参数必须是非空 Markdown。"
            "保存完成后，用中文简洁告知用户文件路径和总结要点。"
        ),
        no_tool_fallback="你还没有保存 Markdown 文件。请先调用 file_write_markdown 保存，再给最终回答。",
        max_steps=max_steps,
        before_tool_call=before_tool_call,
        after_tool_result=after_tool_result,
        on_step_recorded=on_step_recorded,
        start_step_index=start_step_index,
    )


async def run_web_table_export_tool_agent(
    *,
    task_id: str,
    user_input: str,
    max_steps: int = 3,
    on_step_recorded: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    start_step_index: int = 1,
) -> dict[str, Any]:
    return await _run_tool_agent(
        task_id=task_id,
        user_input=user_input,
        allowed_tools=WEB_TABLE_EXPORT_TOOLS,
        system_prompt=(
            "你是 DeskPilot 的网页表格导出 Agent。"
            "你必须通过工具完成任务，而不是假设网页数据。"
            "优先调用 browser_export_table_to_xlsx 抽取当前网页中的 HTML 表格并保存为 Excel。"
            "如果工具返回没有检测到 HTML 表格，再调用 browser_export_structured_blocks_to_xlsx 抽取重复列表或卡片。"
            "调用 browser_export_structured_blocks_to_xlsx 时必须把用户原始需求填入 instruction 参数。"
            "如果用户没有指定文件名，请根据网页或用户任务给出简短中文文件名。"
            "如果两个工具都没有检测到数据，必须如实说明当前网页没有可导出的表格、列表或卡片结构。"
            "保存完成后，用中文简洁告知用户 Excel 文件路径和导出的数据数量。"
        ),
        no_tool_fallback=(
            "你还没有导出 Excel 文件。请先调用 browser_export_table_to_xlsx；"
            "如果没有 HTML 表格，再调用 browser_export_structured_blocks_to_xlsx。"
        ),
        max_steps=max_steps,
        on_step_recorded=on_step_recorded,
        start_step_index=start_step_index,
    )
