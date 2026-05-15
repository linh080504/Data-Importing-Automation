from __future__ import annotations

import csv
import io
from dataclasses import dataclass


@dataclass
class ParsedTemplate:
    columns: list[dict[str, int | str]]
    sample_row: dict[str, str] | None


class TemplateParseError(ValueError):
    pass


def parse_template_csv(content: bytes) -> ParsedTemplate:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise TemplateParseError("Template file must be UTF-8 encoded") from exc

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise TemplateParseError("Template file must include a header row")

    fieldnames = [field.strip() for field in reader.fieldnames if field and field.strip()]
    if not fieldnames:
        raise TemplateParseError("Template file must include at least one column")

    columns = [{"name": name, "order": index} for index, name in enumerate(fieldnames, start=1)]
    first_row = next(reader, None)
    sample_row = None
    if first_row is not None:
        sample_row = {key.strip(): value for key, value in first_row.items() if key and key.strip()}

    return ParsedTemplate(columns=columns, sample_row=sample_row)
