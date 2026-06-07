#!/usr/bin/env python
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

NON_ASCII_RE = re.compile(r"[^\x00-\x7F]")


def is_english_safe(value: str) -> bool:
    if not value or NON_ASCII_RE.search(value):
        return False
    return len(re.findall(r"[A-Za-z]", value)) >= 3


def clean_description(value: str) -> str:
    if not value:
        return value
    sentences = re.split(r"(?<=[.!?])\s+", value)
    kept = [sentence for sentence in sentences if is_english_safe(sentence)]
    return " ".join(kept).strip()[:420]


def normalize_record(record: dict[str, Any]) -> bool:
    changed = False
    contact = str(record.get("contact_person") or "")
    contact_source = str((record.get("sourceUrls") or {}).get("contact_person") or "")
    if contact and (NON_ASCII_RE.search(contact) or not is_english_safe(contact)) and "wikipedia.org" in contact_source:
        record["contact_person"] = ""
        changed = True

    description = str(record.get("description") or "")
    if description and NON_ASCII_RE.search(description):
        cleaned = clean_description(description)
        if cleaned != description:
            record["description"] = cleaned
            changed = True

    name = str(record.get("name") or "")
    source_title = str(record.get("sourceTitle") or "")
    country = str(record.get("countryName") or "")
    if name and NON_ASCII_RE.search(name) and is_english_safe(source_title):
        record["name"] = f"{source_title}, {country}" if country and country not in source_title else source_title
        changed = True
    return changed


def main() -> int:
    root = Path(__file__).resolve().parents[1] / "data" / "runs"
    changed_files = 0
    for path in root.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for record in data.get("records", []):
            changed = normalize_record(record) or changed
        if changed:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed_files += 1
            print(f"normalized {path}")
    print(f"normalized_files={changed_files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
