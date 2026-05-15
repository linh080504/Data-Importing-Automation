from types import SimpleNamespace

from app.services.ai_extractor import AIExtractorOutput, extract_critical_fields, ExtractRequest
from app.services.direct_run import RuleBasedExtractorClient


def test_rule_based_extractor_coerces_list_values_to_scalar() -> None:
    output = extract_critical_fields(
        ExtractRequest(raw_text="{}", critical_fields=["website"]),
        client=RuleBasedExtractorClient({"website": ["https://example.edu"]}, ["website"]),
    )

    assert isinstance(output, AIExtractorOutput)
    assert output.critical_fields["website"].value == "https://example.edu"
