from __future__ import annotations

from dataclasses import dataclass


MIN_CRITICAL_FIELDS = 3
MAX_CRITICAL_FIELDS_MVP = 10

PRIORITY_RULES: list[tuple[tuple[str, ...], int, str]] = [
    (("name",), 100, "Primary entity identifier for display and matching"),
    (("location", "country", "city", "address"), 95, "Core location data is important for import and search"),
    (("website", "url", "link"), 90, "Official source link supports verification and follow-up"),
    (("description", "overview", "summary"), 85, "Descriptive content is valuable and often unstructured"),
    (("financial", "tuition", "fee", "cost"), 82, "Financial information is high-value for users"),
    (("admission", "contact", "phone", "email"), 80, "Contact and admissions fields are important for operations"),
    (("rank", "ranking"), 76, "Ranking data is useful but usually secondary to identity/contact fields"),
    (("student", "faculty", "campus", "housing", "immigration"), 72, "Student-life and campus fields are useful enrichment fields"),
    (("slug",), 20, "Slug can usually be generated rule-based and should not be prioritized"),
    (("id",), 10, "ID is usually system-generated or mapping-specific, not a deep AI extraction target"),
    (("sponsored",), 5, "Sponsored flag is typically defaulted or managed by business rules"),
]


@dataclass
class SuggestedFieldResult:
    name: str
    score: int
    reason: str


def suggest_critical_fields(columns: list[dict]) -> list[SuggestedFieldResult]:
    results: list[SuggestedFieldResult] = []
    for column in columns:
        name = str(column["name"])
        normalized = name.lower()
        best_score = 50
        best_reason = "General template field with moderate value"
        for keywords, score, reason in PRIORITY_RULES:
            if any(keyword in normalized for keyword in keywords):
                if score > best_score:
                    best_score = score
                    best_reason = reason
        results.append(SuggestedFieldResult(name=name, score=best_score, reason=best_reason))

    ranked = sorted(results, key=lambda item: (-item.score, item.name))
    return ranked[:MAX_CRITICAL_FIELDS_MVP]
