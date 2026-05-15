from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field


class DiscoveryUniversitySeed(BaseModel):
    unique_key: str
    name: str | None = None
    country: str | None = None
    website: str | None = None
    location: str | None = None
    source_url: str | None = None
    source_type: Literal["prompt", "trusted_source"] = "trusted_source"
    notes: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)


class DiscoveryPromptResult(BaseModel):
    universities: list[DiscoveryUniversitySeed] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


@dataclass
class DiscoveryRow:
    source_id: str
    source_name: str
    unique_key: str
    normalized: dict[str, Any]
    raw_payload: dict[str, Any]
    raw_text: str


@dataclass
class DiscoverySourceBundle:
    source_id: str
    source_name: str
    rows: list[DiscoveryRow]
