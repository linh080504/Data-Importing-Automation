from __future__ import annotations

import csv
import io

from openpyxl import Workbook

from app.services.export_mapping import map_clean_payload_to_template



def _column_name(column: dict[str, object]) -> str:
    return str(column.get("name") or "").strip()


def _column_order(column: dict[str, object]) -> int:
    value = column.get("order", 0)
    return value if isinstance(value, int) else 0



def build_export_rows(
    clean_records: list[object],
    *,
    template_columns: list[dict[str, object]],
    defaults: dict[str, object] | None = None,
) -> list[dict[str, object | None]]:
    return [
        map_clean_payload_to_template(
            getattr(record, "clean_payload", {}) or {},
            template_columns=template_columns,
            defaults=defaults,
        )
        for record in clean_records
    ]



def _headers(template_columns: list[dict[str, object]]) -> list[str]:
    ordered_columns = sorted(template_columns, key=_column_order)
    return [_column_name(column) for column in ordered_columns if _column_name(column)]



def export_rows_to_csv(
    rows: list[dict[str, object | None]],
    *,
    template_columns: list[dict[str, object]],
) -> bytes:
    headers = _headers(template_columns)

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()

    for row in rows:
        writer.writerow({header: row.get(header) for header in headers})

    return buffer.getvalue().encode("utf-8")



def export_rows_to_xlsx(
    rows: list[dict[str, object | None]],
    *,
    template_columns: list[dict[str, object]],
) -> bytes:
    headers = _headers(template_columns)

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(headers)

    for row in rows:
        worksheet.append([row.get(header) for header in headers])

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()



def export_clean_records_to_csv(
    clean_records: list[object],
    *,
    template_columns: list[dict[str, object]],
    defaults: dict[str, object] | None = None,
) -> bytes:
    rows = build_export_rows(
        clean_records,
        template_columns=template_columns,
        defaults=defaults,
    )
    return export_rows_to_csv(rows, template_columns=template_columns)



def export_clean_records_to_xlsx(
    clean_records: list[object],
    *,
    template_columns: list[dict[str, object]],
    defaults: dict[str, object] | None = None,
) -> bytes:
    rows = build_export_rows(
        clean_records,
        template_columns=template_columns,
        defaults=defaults,
    )
    return export_rows_to_xlsx(rows, template_columns=template_columns)
