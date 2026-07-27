from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from backend.app.agent.providers.capability_detection import (
    ConfiguredStructuredMode,
    ProviderStructuredMode,
    candidate_modes,
)


StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class StructuredOutputError(RuntimeError):
    def __init__(self, message: str, *, attempts: list[str] | None = None) -> None:
        super().__init__(message)
        self.attempts = attempts or []


@dataclass(frozen=True)
class StructuredOutputResult:
    value: BaseModel
    mode: ProviderStructuredMode
    repaired: bool


def extract_json_object(text: str) -> dict[str, Any]:
    candidate = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, re.DOTALL | re.IGNORECASE)
    if fenced:
        candidate = fenced.group(1).strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, character in enumerate(candidate):
            if character != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(candidate[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        raise StructuredOutputError("模型输出中没有可解析的 JSON object。")
    if not isinstance(parsed, dict):
        raise StructuredOutputError("模型结构化输出必须是 JSON object。")
    return parsed


def _response_format(mode: ProviderStructuredMode, model_type: type[BaseModel]) -> dict[str, Any] | None:
    if mode == "native_json_schema":
        return {
            "type": "json_schema",
            "json_schema": {
                "name": model_type.__name__.lower(),
                "strict": True,
                "schema": model_type.model_json_schema(),
            },
        }
    if mode == "json_mode":
        return {"type": "json_object"}
    return None


async def _completion_content(
    client: Any,
    *,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float,
    mode: ProviderStructuredMode,
    model_type: type[BaseModel],
) -> str:
    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "messages": messages,
    }
    response_format = _response_format(mode, model_type)
    if response_format is not None:
        kwargs["response_format"] = response_format
    response = await client.chat.completions.create(**kwargs)
    content = response.choices[0].message.content
    if not isinstance(content, str) or not content.strip():
        raise StructuredOutputError("模型返回了空的结构化输出。")
    return content


async def complete_structured(
    client: Any,
    *,
    model: str,
    messages: list[dict[str, Any]],
    output_model: type[StructuredModel],
    configured_mode: ConfiguredStructuredMode = "auto",
    temperature: float = 0,
) -> StructuredOutputResult:
    attempts: list[str] = []
    last_error: Exception | None = None
    for mode in candidate_modes(configured_mode):
        try:
            content = await _completion_content(
                client,
                model=model,
                messages=list(messages),
                temperature=temperature,
                mode=mode,
                model_type=output_model,
            )
        except StructuredOutputError as exc:
            last_error = exc
            attempts.append(f"{mode}:validation:{exc}")
            content = ""
        except Exception as exc:  # Provider incompatibility, timeout or transport failure.
            last_error = exc
            attempts.append(f"{mode}:provider:{type(exc).__name__}:{exc}")
            if configured_mode == "native":
                break
            continue
        try:
            value = output_model.model_validate(extract_json_object(content))
            return StructuredOutputResult(value=value, mode=mode, repaired=False)
        except (StructuredOutputError, ValidationError, ValueError, TypeError) as exc:
            last_error = exc
            attempts.append(f"{mode}:validation:{exc}")

        # A provider accepted this response mode but produced invalid data. Make
        # exactly one repair request; do not multiply repairs across other modes.
        repair_messages = [
            *messages,
            {"role": "assistant", "content": content},
            {
                "role": "user",
                "content": (
                    "上一条输出不符合要求。只返回一个严格符合 JSON Schema 的 JSON object，"
                    f"不要 Markdown。校验错误：{last_error}"
                ),
            },
        ]
        try:
            repaired_content = await _completion_content(
                client,
                model=model,
                messages=repair_messages,
                temperature=temperature,
                mode=mode,
                model_type=output_model,
            )
            value = output_model.model_validate(extract_json_object(repaired_content))
            return StructuredOutputResult(value=value, mode=mode, repaired=True)
        except Exception as exc:
            last_error = exc
            attempts.append(f"{mode}:repair:{type(exc).__name__}:{exc}")
            break
    raise StructuredOutputError(
        f"模型未能返回有效结构化结果：{last_error or 'unknown error'}",
        attempts=attempts,
    )
