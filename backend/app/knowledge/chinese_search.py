from __future__ import annotations

import re

import jieba


def search_terms(text: str, limit: int = 32) -> list[str]:
    """Return stable Chinese/Latin terms suitable for FTS5 indexing and queries."""
    terms: list[str] = []
    seen: set[str] = set()
    for value in jieba.cut_for_search(text.strip()):
        token = value.strip().casefold()
        if not token or token in seen or not re.search(r"[\w\u4e00-\u9fff]", token):
            continue
        if len(token) == 1 and re.fullmatch(r"[\u4e00-\u9fff]", token):
            continue
        seen.add(token)
        terms.append(token)
        if len(terms) >= limit:
            break
    return terms


def indexed_text(text: str) -> str:
    terms = search_terms(text, 5000)
    return f"{text}\n\n{' '.join(terms)}" if terms else text
