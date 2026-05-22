from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass
from typing import Protocol
import httpx
from bs4 import BeautifulSoup

from app.schemas.ai_output import AIExtractorOutput
from app.services.prompt_rules import build_field_instructions


class AIEnrichmentClientProtocol(Protocol):
    def generate_json(self, *, prompt: str) -> str: ...


@dataclass
class EnrichmentRequest:
    known_fields: dict[str, object]
    missing_fields: list[str]
    country: str | None = None
    location_code: int | None = None


class AIEnrichmentParseError(ValueError):
    pass


def search_duckduckgo(query: str) -> list[dict[str, str]]:
    """
    Searches DuckDuckGo HTML and parses the top results (title, link, snippet).
    Resolves redirects to get direct source URLs (e.g. shiksha.com, collegedunia.com).
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36"
    }
    try:
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"
        response = httpx.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return []
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        for result in soup.find_all("div", class_="result"):
            title_a = result.find("a", class_="result__url")
            snippet_a = result.find("a", class_="result__snippet")
            if title_a:
                title = title_a.text.strip()
                raw_link = title_a["href"]
                # Resolve DuckDuckGo redirect link
                parsed_url = urllib.parse.urlparse(raw_link)
                actual_link = raw_link
                if "duckduckgo.com" in parsed_url.netloc or parsed_url.netloc == "":
                    qs = urllib.parse.parse_qs(parsed_url.query)
                    if "uddg" in qs:
                        actual_link = qs["uddg"][0]
                snippet = snippet_a.text.strip() if snippet_a else ""
                results.append({
                    "title": title,
                    "link": actual_link,
                    "snippet": snippet
                })
        return results
    except Exception:
        return []


def build_enrichment_prompt(request: EnrichmentRequest, search_context: str = "") -> str:
    fields_json = json.dumps(request.missing_fields, ensure_ascii=False)
    known_json = json.dumps(request.known_fields, ensure_ascii=False)
    rules_text = build_field_instructions(country=request.country, location_code=request.location_code)
    
    prompt = (
        "You are a conservative university data enrichment assistant. "
        "Fill ONLY the requested missing fields when you are confident from stable public knowledge, "
        "the provided Web Search Results, or from the provided known fields. "
        "If confidence is below 0.80, return value null and confidence 0. "
        "Do not invent data. Do not create values just to complete the CSV. "
        "Never guess a phone number, email, admissions contact, or named contact person unless it is an exact well-known public value with confidence at least 0.95. "
        "For financials, return only annual tuition/fee/cost amount or range; if you do not know a concrete amount/range, return null. "
        "Format financials strictly as: 'Local Currency ($USD Amount in brackets)' (e.g. 'INR 54k-1.13L ($650-1360)'). "
        "If you use the Web Search Results to fill a field (especially financials), you MUST set 'evidence_url' to the URL of the search result you used, and 'evidence_source' to the website domain name (e.g. 'shiksha.com', 'collegedunia.com' or the school official domain). "
        "Otherwise, if using your internal model memory, set 'evidence_url' to null and 'evidence_source' to 'ai_enrichment_model_memory'. "
        "Return strict JSON with this shape: "
        "{\"critical_fields\": {\"field_name\": {\"value\": ..., \"confidence\": 0.0-1.0, \"source_excerpt\": ..., \"evidence_url\": ..., \"evidence_source\": ..., \"evidence_required\": false}}, \"extraction_notes\": [...]} . "
        "Do not include fields outside the requested list. "
        f"\n{rules_text}\n"
    )
    if search_context:
        prompt += f"\n=== WEB SEARCH EVIDENCE (USE THESE URLS FOR 'evidence_url') ===\n{search_context}\n======================================================\n\n"
        
    prompt += (
        f"Requested missing fields: {fields_json}. "
        f"Known school data: {known_json}"
    )
    return prompt


def parse_enrichment_output(payload: str) -> AIExtractorOutput:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise AIEnrichmentParseError("AI enrichment returned invalid JSON") from exc
    try:
        return AIExtractorOutput.model_validate(data)
    except Exception as exc:
        raise AIEnrichmentParseError("AI enrichment output failed schema validation") from exc


def enrich_missing_fields(
    request: EnrichmentRequest,
    *,
    client: AIEnrichmentClientProtocol,
) -> AIExtractorOutput:
    search_context = ""
    # Perform web search if financials is missing and name is available
    if "financials" in request.missing_fields and request.known_fields.get("name"):
        school_name = str(request.known_fields["name"])
        country_name = str(request.country or "")
        search_query = f"{school_name} {country_name} tuition fees".strip()
        search_results = search_duckduckgo(search_query)
        if search_results:
            search_context = "Web Search Results for tuition fees:\n"
            for idx, res in enumerate(search_results[:5], 1):
                search_context += f"Source [{idx}]: {res['title']}\nURL: {res['link']}\nSnippet: {res['snippet']}\n\n"

    prompt = build_enrichment_prompt(request, search_context=search_context)
    response = client.generate_json(prompt=prompt)
    return parse_enrichment_output(response)

