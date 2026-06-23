"""Robust loader for the University_Import_Clean CSV.

The sample file's header row does NOT line up with its data rows:
- header: ['', 'id', 'name', 'location', ...] (22 columns)
- most data rows: ['', '<name>, <country>', '356', '<description>', ...] (21 cols, no id value)
- first data row: ['<name>, <country>', '356', ...] (20 cols, no leading blank either)

So instead of trusting the header we re-align every row individually using
anchor fields (the website cell must look like a URL, the slug cell like a
slug). Rows that cannot be aligned are kept with suspicious=True and only
their raw cells preserved — they are never silently mis-mapped.
"""

import csv
import json
import logging
import re
from pathlib import Path

from .normalize import (
    clean_text,
    make_slug,
    normalize_bool,
    normalize_email,
    normalize_int,
    normalize_phone,
    normalize_url,
)
from .country_registry import resolve_numeric_country

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "field_mapping.json"

BOOL_FIELDS = {"sponsored", "student_loan_available", "housing_availability", "immigration_support"}
INT_FIELDS = {"number_of_students", "university_campuses"}
URL_FIELDS = {"website", "admissions_page_link"}


def load_mapping_config(path=None) -> dict:
    with open(path or CONFIG_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _find_offset(cells: list[str], config: dict) -> int | None:
    """Find row shift so that cells[offset + anchor.index] matches anchor.pattern."""
    fields = config["canonical_fields"]
    anchors = config["anchor_fields"]
    n_fields = len(fields)
    max_offset = max(0, len(cells) - n_fields + 2)
    for offset in range(0, max_offset + 1):
        ok = True
        for anchor in anchors.values():
            idx = offset + anchor["index"]
            if idx >= len(cells):
                ok = False
                break
            value = (cells[idx] or "").strip()
            # empty anchor cells are tolerated (e.g. missing website), but not all of them
            if value and not re.match(anchor["pattern"], value, re.IGNORECASE):
                ok = False
                break
        if ok:
            # require at least one anchor to be non-empty for a confident match
            non_empty = any(
                (cells[offset + a["index"]] or "").strip()
                for a in anchors.values()
                if offset + a["index"] < len(cells)
            )
            if non_empty:
                return offset
    return None


def parse_csv_rows(csv_path: str, config: dict | None = None) -> list[dict]:
    """Return a list of record dicts: {fields, raw, suspicious, alignment_offset}."""
    config = config or load_mapping_config()
    fields = config["canonical_fields"]
    country_code_overrides = config.get("country_numeric_codes", {})

    records = []
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        rows = list(reader)

    if not rows:
        return records

    header = [c.strip().lower() for c in rows[0]]
    looks_like_header = "name" in header or "slug" in header or "website" in header
    data_rows = rows[1:] if looks_like_header else rows

    for line_no, cells in enumerate(data_rows, start=2 if looks_like_header else 1):
        if not any((c or "").strip() for c in cells):
            continue
        offset = _find_offset(cells, config)
        record = {
            "raw": {"line": line_no, "cells": cells, "header": rows[0] if looks_like_header else None},
            "suspicious": offset is None,
            "alignment_offset": offset,
            "fields": {},
        }
        if offset is not None:
            for i, field in enumerate(fields):
                idx = offset + i
                record["fields"][field] = clean_text(cells[idx]) if idx < len(cells) else ""
            _post_process(record, country_code_overrides)
        else:
            logger.warning("CSV line %s could not be aligned; kept raw only", line_no)
        records.append(record)

    aligned = sum(1 for r in records if not r["suspicious"])
    logger.info("CSV parsed: %s rows, %s aligned, %s suspicious", len(records), aligned, len(records) - aligned)
    return records


def _post_process(record: dict, country_code_overrides: dict):
    f = record["fields"]

    # "VTM NSS College, India" -> name + country
    name = f.get("name", "")
    country_name = ""
    if "," in name:
        head, _, tail = name.rpartition(",")
        tail = tail.strip()
        if tail and len(tail) < 60 and not any(ch.isdigit() for ch in tail):
            f["name"] = head.strip()
            country_name = tail

    # 'location' in the sample holds an ISO 3166-1 numeric country code (e.g. 356)
    loc = f.get("location", "")
    if loc.isdigit():
        normalized_numeric = loc.zfill(3)
        override = country_code_overrides.get(loc) or country_code_overrides.get(normalized_numeric)
        country, code = (
            (override.get("name", ""), override.get("code", ""))
            if override else resolve_numeric_country(normalized_numeric)
        )
        if country or code:
            f["country"] = country
            f["country_code"] = code
            f["location"] = country_name or country
        else:
            f["country"] = country_name
            f["country_code"] = ""
    elif loc:
        f["country"] = country_name
        f["country_code"] = ""
    else:
        f["country"] = country_name
        f["country_code"] = ""

    f["normalized"] = {
        "website": normalize_url(f.get("website")),
        "admissions_page_link": normalize_url(f.get("admissions_page_link")),
        "admissions_contact": normalize_email(f.get("admissions_contact")),
        "admissions_phone": normalize_phone(f.get("admissions_phone")),
        "slug": f.get("slug") or make_slug(f.get("name", "")),
        **{b: normalize_bool(f.get(b)) for b in BOOL_FIELDS},
        **{i: normalize_int(f.get(i)) for i in INT_FIELDS},
    }
