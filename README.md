# Beyondegree — Academic Data ETL Pipeline (MVP)

Country-based end-to-end ETL for higher-education data:

```
country selection → discover institutions → filter higher-education only
→ crawl official websites → extract university fields (+ field-level evidence)
→ extract programs/majors → clean/normalize/validate → review in web UI
→ approve/reject/edit → dry-run import → import into Django DB
```

A standalone Django project (`config` + apps `academic_etl` and `universities`).
The `universities` app holds the target models the importer writes into; if the
real Beyondegree backend lands later, only `academic_etl/services/importer.py`
needs re-pointing.

## Setup

```powershell
cd "D:\work\New folder\beyond_degree"
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser   # optional, for /admin/
```

## Pipeline commands

```powershell
# 0) RECOMMENDED — build a broad, all-English catalog for a country in one shot:
#    Wikipedia list discovery -> English Wikipedia infobox/lead -> official
#    English-site crawl -> validate. (~120 Vietnamese institutions, English data.)
python manage.py build_country_catalog --country "Vietnam"
python manage.py build_country_catalog --country "Vietnam" --max 60 --crawl-limit 30 --dynamic
python manage.py build_country_catalog --country "Vietnam" --no-crawl   # Wikipedia-only, fastest

# 0b) LEGACY API-PRIMARY — Wikipedia roster + Gemini grounded enrichment.
#     Each institution's required fields (name, website, description,
#     campus_student_life, number_of_students) are filled from a Gemini answer
#     grounded in Google Search, with source URLs stored as evidence. Needs
#     GEMINI_API_KEY in a .env file at the project root (see .env.example).
python manage.py build_country_gemini --country "Vietnam"
python manage.py build_country_gemini --country "Vietnam" --max 5        # quick test
python manage.py build_country_gemini --country "Vietnam" --concurrency 4 --no-cache

# 0c) QUOTA-SAVING HYBRID — fill what's FREE first (Wikipedia article + official-
#     site footer/About crawl), then call Gemini ONLY for institutions still
#     missing a required field (skips complete ones; never overwrites free data).
python manage.py build_country_hybrid --country "Vietnam"
python manage.py build_country_hybrid --country "Vietnam" --no-crawl     # Wikipedia + Gemini gaps
python manage.py build_country_hybrid --country "Vietnam" --crawl-limit 30 --dynamic

# 0d) MAJORS (1-to-many) for a run's universities, via Gemini grounded answers
#     (English names + source URL). Run after the universities are staged.
#     Exported separately by the "Majors CSV (simple 3-col)" download:
#     University Name | Major Name | Source URL.
python manage.py enrich_majors_gemini --run-id 17
python manage.py enrich_majors_gemini --run-id 17 --limit 10 --no-cache

# 1) Discover institutions for a country (online, free Hipo Labs API)
python manage.py discover_country_institutions --country "India" --limit 100

# 1w) Or discover from the English Wikipedia country list (broadest, English names)
python manage.py discover_country_institutions --country "Vietnam" --provider wikipedia

# 1a) Or discover from Wikidata/Wikipedia (name, website, city, QID, article URL)
python manage.py discover_country_institutions --country "Vietnam" --provider wikidata --limit 200

# 1b) Or seed straight from the sample CSV (full fields + evidence staged)
python manage.py seed_from_csv --csv "sample_data/University_Import_Clean-7.csv" --country "India"

# 2) Crawl official sites of VALID higher-education seeds
python manage.py crawl_country --country "India" --limit 20            # discover + crawl in one go
python manage.py crawl_country --run-id 1 --limit 5 --max-pages 6      # continue an existing run
python manage.py crawl_country --country-code IN --institution-type university --limit 50
python manage.py crawl_country --country "India" --limit 20 --dynamic  # + Scrapling browser fallback for JS sites

# 3) Validate + score staged records
python manage.py validate_country_run --run-id 1

# 4) Review in the web UI (see below), then import
python manage.py import_country_run --run-id 1 --approved-only --dry-run   # preview only
python manage.py import_country_run --run-id 1 --approved-only             # live import
python manage.py import_country_run --run-id 1 --dry-run                   # confidence-threshold mode (>= 0.75)
```

## Review UI

```powershell
python manage.py runserver
```

Open http://127.0.0.1:8000/etl/

- **Dashboard** `/etl/` — totals + recent runs, plus two "start a run" forms:
  the classic crawl, and **⭐ Build crawl-first catalog** (Wikipedia roster +
  official crawl + AI gap-fill). The background build runs in a thread; the run
  page auto-refreshes to show live progress (`x/total` institutions, staged /
  from-cache / error counts). A **Strategy** dropdown picks **API-primary** (legacy
  mode) or **Hybrid** (crawl free fields first, AI only fills the gaps —
  saves quota). Re-run or resume it from the run page ("Run / resume AI gap-fill");
  cached institutions are skipped so it never re-bills.
- **Delete a run** — a 🗑 Delete button on the runs list and run detail removes
  a run and all its staged data (with a confirm prompt).
- **Pipeline runs** `/etl/runs/`, **run detail** `/etl/runs/<id>/`
- **Discovered institutions** `/etl/runs/<id>/seeds/` (valid / invalid / needs_review)
- **University review** `/etl/runs/<id>/universities/` → per-record page with
  staged value (editable), current DB value, evidence snippet + source URL,
  validation issues, Approve / Reject / Save-edits buttons
- **Program review** `/etl/runs/<id>/programs/` and per-major page with
  field-level evidence + source URL, inline approve/reject/edit
- **Evidence detail** `/etl/evidence/<id>/` — full provenance incl. HTML hash
- **Import preview** `/etl/runs/<id>/import-preview/` — live create/update/skip
  plan with field-level diffs; import job logs at `/etl/import-jobs/<id>/`
- **Approve all valid** — one button on the run page bulk-approves every
  valid/warnings record (leaving `needs_review` for manual review) so the Clean
  pages and CSV export populate without per-record clicking.
- **CSV download** — "⬇ Universities/Majors CSV (English)" buttons (clean +
  English-only) plus "(all)" variants (`?all=1`, every staged row incl.
  non-English/unapproved) on the run detail and clean-data pages. Universities
  export uses the sample-CSV column shape; majors export carries every program
  detail field + provenance.
  Endpoints: `/etl/runs/<id>/export/universities.csv`, `…/export/majors.csv`.

So an operator can run the whole thing from the browser: open a run, review and
approve records, then click the two download buttons to get a universities CSV
and a per-university majors CSV. Real Vietnam sample output produced this way is
checked in under `sample_output/`.

Django admin at `/admin/` exposes all staging tables too.

## End-to-end on real Vietnam data (no mock)

```powershell
python manage.py crawl_country --country "Vietnam" --provider wikidata --limit 8 --max-pages 8
python manage.py validate_country_run --run-id <id>
python manage.py runserver        # review + approve at /etl/runs/<id>/universities/
# then click "⬇ Universities CSV" / "⬇ Majors CSV" on /etl/runs/<id>/
```

Add `--dynamic` to the crawl for JS-rendered sites (needs `scrapling install`).

## Quick test with the sample CSV

```powershell
python manage.py seed_from_csv --csv "sample_data/University_Import_Clean-7.csv" --country "India"
python manage.py crawl_country --run-id 1 --limit 2 --max-pages 6
python manage.py validate_country_run --run-id 1
python manage.py runserver        # approve a few records at /etl/runs/1/universities/
python manage.py import_country_run --run-id 1 --approved-only --dry-run
python manage.py import_country_run --run-id 1 --approved-only
```

Run the test suite (54 tests, no network needed — crawlers/Wikidata are mocked):

```powershell
python manage.py test academic_etl
```

## How it works

- **Wikipedia discovery** (`services/wikipedia.py`): `WikipediaListProvider`
  resolves a country's English-Wikipedia list article (`List of universities in
  <country>`) via the MediaWiki parse API and extracts every linked institution
  (article title = English name, plus article URL). Far broader than Wikidata
  (~120 for Vietnam vs ~26) and English by construction. City/ministry/"List of…"
  noise is filtered; the rest is gated by `classify_institution`.
- **Wikipedia article extraction** (`services/wikipedia_extract.py`): for each
  institution, the English article's infobox (website, students→`number_of_students`,
  location→`city`) and lead paragraph (`description`, native-language parentheticals
  stripped) are mined into `ExtractedUniversity` with `FieldEvidence`. This English
  backbone is staged first (`pipeline.enrich_run_from_wikipedia`, articles fetched
  concurrently via `services/fetch_pool`), then the official **English** site is
  crawled to add admissions/programs/tuition (crawl only fills empty fields, so the
  English values win).
- **Gemini grounded enrichment** (`services/gemini_enrich.py`): asks Gemini with
  the `google_search` grounding tool — so each answer is built from live search
  results, not one site's raw HTML — and parses a strict JSON object out of the
  grounded reply. Fields filled: name, website, description, campus_student_life,
  number_of_students, financials (formatted `VND 20m-40m ($800-1600)` using the
  country's currency), student_to_faculty_ratio, global_rank (QS/THE world rank),
  admissions_contact/admissions_phone/admissions_page_link (from the official
  site footer/contact page). Grounding source URLs are stored as `FieldEvidence`
  (`extraction_method="gemini_grounding"`, confidence 0.85). Unverifiable fields
  are returned `null`/empty (never fabricated). `location` (ISO 3166-1 numeric
  code, e.g. 704 for Vietnam), `sponsored` (0) and the other boolean columns are
  set deterministically to match the sample CSV. Responses are cached under
  `var/gemini_cache/` (keyed by name+country) so re-runs don't re-bill.
  **Quota/keys:** the free tier caps each model at ~20 requests/day/key, counted
  per (key, model); `GEMINI_API_KEYS` (comma-separated) and a `GEMINI_MODEL`
  fallback chain rotate across buckets — invalid/expired keys and daily-exhausted
  buckets are skipped automatically. A key must be a real API key (`AIzaSy…`); an
  `AQ.`/`ya29.` OAuth token expires in ~1h and fails with 401. Wired by
  `pipeline.enrich_run_from_gemini` and the `build_country_gemini` command, using
  the Wikipedia list as the institution roster.
- **English-only catalog** (`services/lang.py`): `is_english` flags non-English
  values; validation marks such records `needs_review` (`non_english` issue) and
  the CSV export excludes them, so the deliverable is one language. `?all=1`
  exports everything for debugging.
- **Wikidata discovery** (`services/wikidata.py`): `WikidataSeedProvider` queries
  the Wikidata Query Service (SPARQL) for higher-education institutions
  (`P31/P279* wd:Q38723`) located in a country, matched by ISO alpha-2 code
  (`P297`) so no country→QID map is needed. Collects name, country + code,
  city/region (`P131`), official website (`P856`, with wikipedia.org/wikidata.org
  rejected), Wikipedia article URL, and the Wikidata QID into each
  `InstitutionSeed` (`wikidata_qid`, `wikipedia_url`). Rows are deduplicated by
  QID → official domain → normalized name + country + city/region, both within a
  batch and against existing seeds in the run. Confidence is a metadata-
  completeness score (floor 0.6, +website/+wikipedia/+place).
- **CSV loader** (`services/csv_seed.py`): the sample CSV's header row is
  misaligned vs its data rows (the `id` column actually holds the name, etc.).
  Rows are re-aligned individually using anchor-field patterns (website URL at
  canonical index 5, slug at index 3) configured in
  `academic_etl/config/field_mapping.json`. Unalignable rows are kept with
  `suspicious=True` and raw cells preserved in `raw_json` — never mis-mapped.
  UTF-8-as-cp1252 mojibake ("â€”") is repaired.
- **Classification** (`services/classification.py`): keyword rules map names to
  institution types. Universities/colleges/institutes/polytechnics/graduate
  schools etc. are valid; high schools, language centers, coaching centers,
  bootcamps are invalid and never crawled; ambiguous names get `needs_review`
  and are never auto-imported.
- **Crawler** (`services/crawler.py`): requests + BeautifulSoup, per-domain
  rate limit (1.5 s), 15 s timeout, 2 retries, robots.txt respected, depth ≤ 2,
  ≤ 12 pages/site, raw HTML cached under `var/html_cache/<sha256>.html`.
  Follows only links classified as admissions/programs/departments/tuition/
  scholarships/international/campus-life/about/contact.
- **English-first crawling** (`ETL_PREFER_ENGLISH`, on by default): when a
  homepage advertises an English version — an `hreflang="en"` alternate or an
  "English"/`/en/` language-switcher link — the crawl hops to that English root
  (incl. `en.` subdomains) and stops following other-language (`/vi/`, `/zh/`…)
  duplicates. This builds a single-language (English) catalog straight from each
  site, no machine translation needed. Sites with no English version are still
  crawled in their own language and surfaced for review.
- **Scrapling fallback** (`services/scrapling_fetch.py`): for JS-rendered
  (React/Next/Angular) sites, a static GET returns an empty SPA shell. Following
  the Scrapling agent-skill escalation rule, when the static HTML has less than
  `ETL_DYNAMIC_MIN_TEXT_CHARS` (500) of visible text, the crawler re-renders the
  page with Scrapling's headless `DynamicFetcher` (Playwright/Chromium) and keeps
  whichever HTML has more text. Off by default; enable per run with
  `crawl_country --dynamic` (or `ETL_USE_DYNAMIC_FALLBACK = True`). The wrapper
  lazy-imports Scrapling and degrades to the static result if the browsers
  aren't installed, so the pipeline never hard-fails. Each `CrawledPage` records
  `render_engine` (`requests` / `scrapling_dynamic`) for provenance.
- **Extraction** (`services/extraction.py`): rule-based (h1/title/meta name,
  email/phone regex, tuition/fee sentence, campus-life paragraphs, international-
  student ratio, keyword link discovery, degree-level patterns — English **and**
  Vietnamese, e.g. cử nhân/thạc sĩ/tiến sĩ). Every field gets a `FieldEvidence`
  row. Programs are accepted only for higher-ed degree levels; short courses/
  workshops/language prep/certificates (incl. chứng chỉ, khóa học ngắn hạn) are
  flagged non-degree, and news/announcement titles (thông báo, lễ, luận án…) are
  dropped as non-programs.
- **Program detail crawling** (`services/program_detail.py`): each discovered
  program/major link is fetched (same domain, bounded by
  `ETL_MAX_PROGRAM_DETAIL_PAGES`, reusing `SiteCrawler.fetch` + the Scrapling
  dynamic fallback when `--dynamic`) and parsed for program_name, degree_level,
  field_of_study, faculty_or_school, description, duration, study_mode, language,
  tuition_fee, currency, intake, application_deadline, admission_requirements,
  career_outcomes, accreditation, program_url, source_url — from `<dt>/<dd>`,
  tables, "Label: value" text and labelled sections (English + Vietnamese
  labels). Every field gets a `FieldEvidence` row; the richer text re-classifies
  the degree level and routes non-degree offerings to `needs_review`.
- **Cross-source reconciliation** (`services/reconcile.py`): for seeds from a
  knowledge base (Wikidata/Wikipedia), the KB-asserted name/website/location are
  recorded as `FieldEvidence` at a **lower confidence (0.5)** than official-
  website extraction (name ≥ 0.6; a homepage-resolve `website` evidence at 0.9),
  so the official site always ranks first and wins on import. When the KB value
  disagrees with the official site (name mismatch, or homepage domain ≠ the KB
  website domain) the field is listed in `normalized_json["source_conflicts"]`;
  validation then raises a `source_conflict` issue and forces the record to
  `needs_review`. The university review page shows KB-source vs official-site
  evidence side by side with a conflict badge.
- **Validation** (`services/validation.py`): required fields, URL/email/phone
  formats, slug shape, in-run duplicate detection (domain / slug /
  name+location, university+program+level), completeness + confidence scores,
  `ValidationIssue` rows.
- **Import** (`services/importer.py`): only approved records (or, without
  `--approved-only`, confidence ≥ threshold and valid/warnings); `needs_review`,
  rejected, invalid and non-higher-ed programs are never imported. Upsert
  order: external id → slug → website domain → name+location (programs:
  university + normalized name + degree level). Existing non-empty values are
  only overwritten by confidence ≥ 0.8 data, never by empty values. Dry-run
  writes `would_create`/`would_update` ImportLogs with `diff_json` and touches
  nothing.

## Known limitations (MVP)

- Rule-based extraction only. JS-heavy sites are handled by the optional
  Scrapling `DynamicFetcher` fallback (`--dynamic`); without it they return
  little content. The fallback needs Playwright browsers (`scrapling install`).
- Program metadata (duration, tuition, intake, requirements) is extracted from
  program detail pages when the site exposes it as labelled fields/tables;
  coverage varies (many Vietnamese program pages use prose, images, or PDFs, so
  name/level/URL remain the most reliable). Everything is reviewable before export.
- Hipo Labs API has no institution-type metadata, so type comes from name
  keywords; some colleges are actually secondary schools (caught at review).
- Discovery providers: Hipo Labs, CSV, Wikidata, and Wikipedia (broadest). A
  country's Wikipedia list article may also link foreign partner universities;
  those are staged and reviewable but not country-filtered yet.
- Crawl is sequential (no concurrency) — fine for ≤ 50 sites per run.
- Output language: the crawler prefers each site's English version, so most data
  lands in English. Sites that publish no English version stay in their own
  language (flagged for review); there is no machine-translation fallback.
- No auth on the review UI (assumed internal/localhost use).

## Next improvements

1. ~~Add a Scrapling `DynamicFetcher` fallback for JS-rendered sites.~~ ✅ Done
   (`services/scrapling_fetch.py`, enable with `crawl_country --dynamic`).
   Next: a `StealthyFetcher` tier for Cloudflare-protected sites.
2. ~~Program detail-page crawling (follow each program link, extract duration/
   fees/requirements with per-field evidence).~~ ✅ Done
   (`services/program_detail.py`). Next: table/PDF and prose parsing for sites
   that don't use labelled fields; per-program detail confidence calibration.
3. ~~Wikidata/Wikipedia discovery provider.~~ ✅ Done (`services/wikidata.py`,
   `discover_country_institutions --provider wikidata`). Next: enrich with
   institution-type facts (P31 subclass) and `P571` inception for ranking.
4. Field-level approve/reject (currently record-level with field editing).
5. Concurrency (httpx + asyncio) and resumable crawls.
6. Point the importer at the real Beyondegree production models.
