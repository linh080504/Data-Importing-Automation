from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from app.schemas.discovery import DiscoveryPromptResult, DiscoveryRow, DiscoverySourceBundle
from app.services.prompt_templates import build_country_prompt


class DiscoveryPromptClientProtocol(Protocol):
    def generate_json(self, *, prompt: str) -> str: ...


@dataclass
class PromptDiscoveryRequest:
    country: str
    critical_fields: list[str]
    prompt_text: str


class PromptDiscoveryParseError(ValueError):
    pass


PROMPT_SOURCE_ID = "prompt-discovery"
PROMPT_SOURCE_NAME = "Prompt Discovery"


def parse_prompt_discovery_output(payload: str) -> DiscoveryPromptResult:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise PromptDiscoveryParseError("Prompt discovery returned invalid JSON") from exc

    try:
        return DiscoveryPromptResult.model_validate(data)
    except Exception as exc:
        raise PromptDiscoveryParseError("Prompt discovery output failed schema validation") from exc


def discover_universities_from_prompt(
    request: PromptDiscoveryRequest,
    *,
    client: DiscoveryPromptClientProtocol,
) -> DiscoveryPromptResult:
    prompt = build_country_prompt(
        country=request.country,
        critical_fields=request.critical_fields,
        user_prompt=request.prompt_text,
    )
    response = client.generate_json(prompt=prompt)
    return parse_prompt_discovery_output(response)


def prompt_result_to_bundle(result: DiscoveryPromptResult) -> DiscoverySourceBundle:
    rows: list[DiscoveryRow] = []
    for university in result.universities:
        payload = dict(university.payload)
        payload.setdefault("name", university.name)
        payload.setdefault("country", university.country)
        payload.setdefault("website", university.website)
        payload.setdefault("location", university.location)
        payload.setdefault("source_url", university.source_url)
        payload.setdefault("notes", list(university.notes))
        raw_text_parts = [
            university.name or "",
            university.country or "",
            university.location or "",
            university.website or "",
            university.source_url or "",
            " ".join(university.notes),
            json.dumps(payload, ensure_ascii=False),
        ]
        rows.append(
            DiscoveryRow(
                source_id=PROMPT_SOURCE_ID,
                source_name=PROMPT_SOURCE_NAME,
                unique_key=university.unique_key,
                normalized={
                    "name": university.name,
                    "country": university.country,
                    "website": university.website,
                    "location": university.location,
                    **payload,
                },
                raw_payload={
                    "name": university.name,
                    "country": university.country,
                    "website": university.website,
                    "location": university.location,
                    "source_url": university.source_url,
                    "notes": university.notes,
                    **payload,
                },
                raw_text="\n".join(part for part in raw_text_parts if part),
            )
        )

    return DiscoverySourceBundle(
        source_id=PROMPT_SOURCE_ID,
        source_name=PROMPT_SOURCE_NAME,
        rows=rows,
    )
