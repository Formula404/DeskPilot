from __future__ import annotations

from fastapi import APIRouter

from backend.app.tools.registry import tool_registry

router = APIRouter(tags=["tools"])


@router.get("/tools")
def list_tools() -> dict:
    return {
        "tools": [
            {
                "name": tool.name,
                "openai_name": tool.openai_name,
                "risk_level": tool.risk_level,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in tool_registry.list()
        ]
    }
