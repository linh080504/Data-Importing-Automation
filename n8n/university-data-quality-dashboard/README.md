# n8n University Data Quality Dashboard

This artifact implements an n8n-only workflow set for crawling university data, scoring data quality, reviewing records, and exporting the fixed-order import CSV.

## Files

- `quality-rules.js` - shared validation, scoring, status, duplicate, evidence, and CSV export logic.
- `dashboard.html` - source SPA served by n8n through `GET /university-dashboard`.
- `data-table-schema.json` - required n8n Data Table schemas.
- `build_workflows.py` - generator for importable n8n workflow JSON files.
- `workflows/*.json` - generated n8n workflows ready to import.

## Import order

1. Create the five n8n Data Tables from `data-table-schema.json`.
2. Import `workflows/00_university_data_tables_setup.json` if you want the schema visible inside n8n.
3. Import the remaining workflow JSON files:
   - `01_university_dashboard_ui.json`
   - `02_university_quality_api.json`
   - `03_university_import_runner.json`
   - `04_university_record_update.json`
   - `05_university_bulk_status.json`
   - `06_university_rerun_checks.json`
   - `07_csv_download.json`
4. Open each Data Table node and reselect the matching table by name if your n8n instance does not resolve the table reference automatically.
5. Activate the webhook workflows.

## Data Tables

Required table names:

- `university_import_runs`
- `university_records`
- `university_quality_findings`
- `university_review_audit`
- `country_crawl_state`

`university_records` contains every fixed CSV column plus quality, evidence, review, and run metadata. Only the fixed CSV columns are exported.

## Endpoints

Production webhook paths:

- `GET /webhook/university-dashboard` - dashboard SPA.
- `GET /webhook/university-quality-api` - dashboard data payload.
- `POST /webhook/university-import-runner` - crawl Wikipedia country list pages and upsert records.
- `POST /webhook/university-record-update` - save one edited record and audit row.
- `POST /webhook/university-bulk-status` - bulk review status update and audit rows.
- `POST /webhook/university-rerun-checks` - recompute scores for all records.
- `GET /webhook/university-csv-download` - returns `University_Import_Clean.csv`.

For test executions, n8n uses `/webhook-test/...`; the dashboard detects that path automatically.

## Import runner body

Example payload:

```json
{
  "countries": ["India"],
  "limit_countries": 1,
  "limit_per_country": 50
}
```

The runner uses the Wikipedia MediaWiki API:

1. Fetch `Lists_of_universities_and_colleges_by_country`.
2. Select matching country list pages.
3. Extract likely institution page titles.
4. Fetch page evidence and external links.
5. Normalize into the fixed CSV schema.
6. Score quality and write records/findings/run summary into Data Tables.

## Quality scoring

Score is `0-100`:

- Schema/type validity: 20
- Field completeness: 20
- Source evidence strength: 25
- Website/contact/admissions verification: 15
- Cross-field consistency/outlier checks: 10
- Duplicate/slug uniqueness: 10

Status rules:

- `Verified`: score >= 85 and official-site or Wikidata evidence exists.
- `Probable`: score 70-84 with no critical schema errors.
- `Needs Review`: score 45-69 or important missing fields.
- `Risky`: score < 45, duplicate conflict, invalid source, or strong contradiction.

`truth_status` is evidence confidence. It is not an absolute fraud accusation unless contradiction rules flag the row.

## Export rule

CSV header order is fixed:

```text
id,name,location,description,slug,sponsored,website,global_rank,financials,student_loan_available,campus_student_life,number_of_students,student_to_faculty_ratio,international_student_ratio,housing_availability,admissions_contact,admissions_phone,contact_person,admissions_page_link,immigration_support,university_campuses
```

The CSV download exports only rows that are approved and valid:

- `review_status` is `Approved` or `export_approved` is `1`.
- score is at least 70.
- no critical schema findings.
- header order passes validation.

The response filename is always `University_Import_Clean.csv`.

## Dashboard

The dashboard is a single-page app served by n8n. It includes:

- Overview KPIs and status/source/score charts.
- Field completeness heatmap.
- Schema, URL, email, phone, admissions, and numeric outlier findings.
- Evidence confidence and risk flags.
- Review queue filters for country, status, score band, missing field, source type, and risky rows.
- Record editor for all fixed CSV columns, evidence links, reviewer note, and audit logging.
- Bulk review actions.
- Export center with exportable/blocked row preview and CSV download.

## Regenerate workflows

After editing `dashboard.html` or `quality-rules.js`, regenerate workflow JSON:

```powershell
python n8n\university-data-quality-dashboard\build_workflows.py
```

This does not run the crawler and does not call Wikipedia. It only writes JSON files under `workflows/`.
