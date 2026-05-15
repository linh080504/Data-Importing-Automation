from __future__ import annotations

PDF_MULTI_ROW_PROMPT_TEMPLATE = """
You are building a structured university discovery dataset for {country}.

Goal:
- Identify universities and colleges relevant to the requested country.
- Return structured rows for downstream extraction and QA.
- Prioritize official and trustworthy sources when possible.

Fields of interest:
{critical_fields}

Requirements:
- Return strict JSON only.
- Use this shape:
{{
  "universities": [
    {{
      "unique_key": "stable-country-specific-key",
      "name": "...",
      "country": "{country}",
      "website": "https://... or null",
      "location": "city/region or null",
      "source_url": "https://... or null",
      "source_type": "prompt",
      "notes": ["short provenance notes"],
      "payload": {{"ranking": null, "tuition": null, "admissions": null}}
    }}
  ],
  "notes": ["summary notes"]
}}

Rules:
- Prefer institutions that are likely to have an official website.
- Include candidate schools even if some requested fields are missing.
- Do not invent values; use null when uncertain.
- Keep notes short and factual.
""".strip()


def build_country_prompt(*, country: str, critical_fields: list[str], user_prompt: str) -> str:
    fields = ", ".join(critical_fields) if critical_fields else "name, website, location"
    return (
        PDF_MULTI_ROW_PROMPT_TEMPLATE.format(country=country, critical_fields=fields)
        + "\n\n"
        + "Additional operator instructions:\n"
        + user_prompt.strip()
    )
