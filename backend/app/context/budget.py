from __future__ import annotations

import json
from typing import Any

from backend.app.context.models import ContextBlock


def estimate_tokens(value: Any) -> int:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    # Deterministic conservative estimate that works for mixed Chinese and Latin text.
    return max(1, (len(text) + 2) // 3)


class ContextBudgeter:
    def select(self, blocks: list[ContextBlock], *, max_tokens: int) -> tuple[list[ContextBlock], dict[str, Any]]:
        prepared: list[ContextBlock] = []
        for block in blocks:
            item = dict(block)
            item["token_estimate"] = int(item.get("token_estimate") or estimate_tokens(item.get("content")))
            prepared.append(item)

        required = [block for block in prepared if block.get("required")]
        optional = [block for block in prepared if not block.get("required")]
        optional.sort(
            key=lambda block: (
                -float(block.get("relevance_score") or 0),
                str(block.get("captured_at") or ""),
                str(block.get("id") or ""),
            )
        )
        selected: list[ContextBlock] = []
        used = 0
        truncated_count = 0
        for block in [*required, *optional]:
            size = int(block.get("token_estimate") or 0)
            if used + size <= max_tokens or block.get("required"):
                selected.append(block)
                used += size
                continue
            content = block.get("content")
            remaining = max_tokens - used
            if isinstance(content, str) and remaining >= 80:
                shortened = content[: remaining * 3]
                item = dict(block)
                item["content"] = shortened + "\n[上下文已按预算截断]"
                item["token_estimate"] = estimate_tokens(item["content"])
                item["truncated"] = True
                selected.append(item)
                used += int(item["token_estimate"])
                truncated_count += 1
            else:
                truncated_count += 1
        return selected, {
            "max_tokens": max_tokens,
            "used_tokens": used,
            "selected_blocks": len(selected),
            "dropped_or_truncated_blocks": truncated_count,
            "reserved_output_tokens": 3500,
        }

