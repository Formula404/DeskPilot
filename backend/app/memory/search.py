from __future__ import annotations

from backend.app.memory.repository import search_memory


def retrieve_memory_refs(query: str) -> list[dict]:
    return search_memory(query)
