from app.services.importer import upsert_import_records


def test_upsert_import_records_inserts_and_updates_by_unique_key() -> None:
    result = upsert_import_records(
        existing_records=[
            {"unique_key": "row-1", "name": "Old University", "website": "https://old.edu"},
        ],
        incoming_records=[
            {"unique_key": "row-1", "name": "Example University", "website": "https://example.edu"},
            {"unique_key": "row-2", "name": "Sample Institute", "website": "https://sample.edu"},
        ],
    )

    assert result.inserted == 1
    assert result.updated == 1
    assert result.duplicates == 0
    assert {record["unique_key"] for record in result.records} == {"row-1", "row-2"}
    assert next(record for record in result.records if record["unique_key"] == "row-1")["name"] == "Example University"



def test_upsert_import_records_counts_duplicate_incoming_keys() -> None:
    result = upsert_import_records(
        existing_records=[],
        incoming_records=[
            {"unique_key": "row-1", "name": "Example University"},
            {"unique_key": "row-1", "name": "Example University Duplicate"},
        ],
    )

    assert result.inserted == 1
    assert result.updated == 0
    assert result.duplicates == 1
    assert len(result.records) == 1
    assert result.records[0]["name"] == "Example University"



def test_upsert_import_records_ignores_missing_unique_key() -> None:
    result = upsert_import_records(
        existing_records=[{"unique_key": "row-1", "name": "Existing"}],
        incoming_records=[
            {"name": "Missing key"},
            {"unique_key": None, "name": "Also missing"},
        ],
    )

    assert result.inserted == 0
    assert result.updated == 0
    assert result.duplicates == 0
    assert result.records == [{"unique_key": "row-1", "name": "Existing"}]
