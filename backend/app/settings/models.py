from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


class AISettings(BaseModel):
    provider: Literal["openai_compatible"] = "openai_compatible"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4.1-mini"
    temperature: float = Field(default=0.2, ge=0, le=2)
    request_timeout_seconds: int = Field(default=60, ge=5, le=600)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        HttpUrl(normalized)
        return normalized

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("模型名称不能为空")
        return normalized


class GeneralSettings(BaseModel):
    response_language: Literal["zh-CN", "en"] = "zh-CN"
    motion_mode: Literal["system", "reduced", "full"] = "system"


class ManagerSettings(BaseModel):
    enabled: bool = True
    model: str | None = None
    timeout_seconds: int = Field(default=15, ge=5, le=120)
    max_delegations: int = Field(default=8, ge=1, le=32)
    max_manager_turns: int = Field(default=10, ge=1, le=32)
    structured_output_mode: Literal["auto", "native", "json"] = "auto"
    clarification_confidence_threshold: float = Field(default=0.65, ge=0, le=1)

    @field_validator("model")
    @classmethod
    def normalize_optional_model(cls, value: str | None) -> str | None:
        normalized = (value or "").strip()
        return normalized or None


class SpecialistSettings(BaseModel):
    model: str | None = None
    timeout_seconds: int = Field(default=30, ge=5, le=300)
    max_tool_steps: int = Field(default=6, ge=1, le=20)

    @field_validator("model")
    @classmethod
    def normalize_specialist_model(cls, value: str | None) -> str | None:
        normalized = (value or "").strip()
        return normalized or None


class SpecialistGroupSettings(BaseModel):
    web: SpecialistSettings = Field(default_factory=SpecialistSettings)
    knowledge: SpecialistSettings = Field(default_factory=SpecialistSettings)
    file: SpecialistSettings = Field(default_factory=SpecialistSettings)
    desktop: SpecialistSettings = Field(default_factory=SpecialistSettings)


class ApplicationSettings(BaseModel):
    schema_version: int = 1
    ai: AISettings = Field(default_factory=AISettings)
    general: GeneralSettings = Field(default_factory=GeneralSettings)
    manager: ManagerSettings = Field(default_factory=ManagerSettings)
    specialists: SpecialistGroupSettings = Field(default_factory=SpecialistGroupSettings)


class RuntimeAISettings(AISettings):
    api_key: str | None = None


class RuntimeApplicationSettings(BaseModel):
    schema_version: int = 1
    ai: RuntimeAISettings = Field(default_factory=RuntimeAISettings)
    general: GeneralSettings = Field(default_factory=GeneralSettings)
    manager: ManagerSettings = Field(default_factory=ManagerSettings)
    specialists: SpecialistGroupSettings = Field(default_factory=SpecialistGroupSettings)

    @property
    def openai_api_key(self) -> str | None:
        return self.ai.api_key

    @property
    def openai_base_url(self) -> str:
        return self.ai.base_url

    @property
    def openai_model(self) -> str:
        return self.ai.model

    @property
    def temperature(self) -> float:
        return self.ai.temperature

    @property
    def request_timeout_seconds(self) -> int:
        return self.ai.request_timeout_seconds


class AISettingsUpdate(AISettings):
    api_key: str | None = Field(default=None, max_length=4096)


class ApplicationSettingsUpdate(BaseModel):
    schema_version: int = 1
    ai: AISettingsUpdate
    general: GeneralSettings
    manager: ManagerSettings = Field(default_factory=ManagerSettings)
    specialists: SpecialistGroupSettings = Field(default_factory=SpecialistGroupSettings)


class PublicAISettings(AISettings):
    api_key_configured: bool
    api_key_hint: str | None = None


class PublicApplicationSettings(BaseModel):
    schema_version: int
    ai: PublicAISettings
    general: GeneralSettings
    manager: ManagerSettings
    specialists: SpecialistGroupSettings
