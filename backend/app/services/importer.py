from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ImportUpsertResult:
    inserted: int
    updated: int
    duplicates: int
    records: list[dict[str, object]]


def _unique_key(record: dict[str, object], unique_key_field: str) -> str:
    value = record.get(unique_key_field)
    return "" if value is None else str(value)


def upsert_import_records(
    existing_records: list[dict[str, object]],
    incoming_records: list[dict[str, object]],
    *,
    unique_key_field: str = "unique_key",
) -> ImportUpsertResult:
    existing_by_key: dict[str, dict[str, object]] = {
        _unique_key(record, unique_key_field): dict(record)
        for record in existing_records
        if _unique_key(record, unique_key_field)
    }

    inserted = 0
    updated = 0
    duplicates = 0
    seen_incoming: set[str] = set()

    for record in incoming_records:
        key = _unique_key(record, unique_key_field)
        if not key:
            continue

        if key in seen_incoming:
            duplicates += 1
            continue

        seen_incoming.add(key)
        existing_record = existing_by_key.get(key)
        if existing_record is None:
            inserted += 1
        else:
            updated += 1

        existing_by_key[key] = dict(record)

    return ImportUpsertResult(
        inserted=inserted,
        updated=updated,
        duplicates=duplicates,
        records=list(existing_by_key.values()),
    )
