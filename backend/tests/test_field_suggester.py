from app.services.field_suggester import suggest_critical_fields


def test_suggest_critical_fields_prioritizes_high_value_columns() -> None:
    columns = [
        {"name": "id", "order": 1},
        {"name": "name", "order": 2},
        {"name": "location", "order": 3},
        {"name": "website", "order": 4},
        {"name": "slug", "order": 5},
        {"name": "description", "order": 6},
        {"name": "admissions_contact", "order": 7},
    ]

    suggestions = suggest_critical_fields(columns)
    names = [item.name for item in suggestions]

    assert names.index("name") < names.index("slug")
    assert "website" in names
    assert "admissions_contact" in names
