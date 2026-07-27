from __future__ import annotations

from typing import Literal


ConfiguredStructuredMode = Literal["auto", "native", "json"]
ProviderStructuredMode = Literal["native_json_schema", "json_mode", "plain_json"]


def candidate_modes(configured: ConfiguredStructuredMode) -> list[ProviderStructuredMode]:
    if configured == "native":
        return ["native_json_schema"]
    if configured == "json":
        return ["json_mode", "plain_json"]
    return ["native_json_schema", "json_mode", "plain_json"]

