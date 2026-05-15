import pytest

from app.services.template_parser import TemplateParseError, parse_template_csv


def test_parse_template_csv_reads_header_and_sample_row() -> None:
    content = b"id,name,website\n1,Example University,https://example.edu\n"

    parsed = parse_template_csv(content)

    assert parsed.columns == [
        {"name": "id", "order": 1},
        {"name": "name", "order": 2},
        {"name": "website", "order": 3},
    ]
    assert parsed.sample_row == {
        "id": "1",
        "name": "Example University",
        "website": "https://example.edu",
    }


def test_parse_template_csv_requires_header() -> None:
    with pytest.raises(TemplateParseError):
        parse_template_csv(b"")
