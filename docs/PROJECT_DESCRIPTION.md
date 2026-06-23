# Beyond Degree - Global University Data ETL Pipeline

## 1. Project Overview

**Beyond Degree** is an automated ETL (Extract - Transform - Load) system that collects university data globally, building a standardized database for searching and comparing higher-education institutions.

### Objectives
- Collect university data from multiple sources (Wikipedia, Wikidata, QS Rankings, official websites)
- Enrich data using AI (Fanar API, Google Gemini) for institutions with missing information
- Standardize data into a unified format (ISO codes, E.164 phone, financial format)
- Support multiple countries (India, Vietnam, USA, Japan, Korea, etc.)
- Export clean CSV for import into production systems

### Tech Stack
| Component | Technology |
|-----------|-----------|
| Backend | Django 6.0 (Python 3.13) |
| Database | SQLite (development) |
| AI Providers | Fanar API (Qatar, 50 req/min × 6 models), Google Gemini (grounded search) |
| Web Scraping | BeautifulSoup4, Requests |
| Frontend | Django Templates, Chart.js 4 |

---

## 2. System Architecture

### 6-Step Pipeline (Click-and-Forget)

```
Step 1: Discovery (Wikipedia + Wikidata + UniRank)
   → Find list of universities by country
   → Output: InstitutionSeed (name, website, Wikipedia URL)

Step 2: Web Scraping (Wikipedia Infobox + QS + Official Site)
   → Multi-page crawl: Homepage + Contact + Student Life + Admissions + About
   → Output: ExtractedUniversity (basic fields)

Step 3: Programs Extraction (Official Website + Wikipedia)
   → Crawl Academics/Programs pages, follow up to 5 links
   → Output: ExtractedProgram

Step 4: AI Gap-Fill (Fanar round-robin 6 models → Gemini fallback)
   → Fill missing fields: financials, campus_life, ranking, booleans
   → Pre-AI cleanup: clear non-English text, short values

Step 5: AI Majors (Fanar/Gemini)
   → Fill programs for universities with < 5 majors
   → 3-level hierarchy: field_of_study → program_name → specializations

Step 6: Post-process + Validate + Auto-approve
   → Normalize phone (E.164), email, URLs
   → Standardize financials format: "INR 50k-200k ($600-2400)"
   → Apply boolean defaults, set sponsored=False
   → Smart dedup: same name + same city = duplicate
   → Auto-approve: critical fields filled + confidence >= 0.5
```

### Data Model (3-Level Hierarchy)

```
ExtractedUniversity (22 fields)
├── name, website, description, location (ISO numeric)
├── financials: "INR 50k-200k ($600-2400)"
├── campus_student_life: 2-3 detailed sentences (English)
├── admissions_contact, admissions_phone (+91...), contact_person
├── global_rank: "QS 150" or "THE 801-1000"
├── housing_availability, student_loan_available, immigration_support (bool)
├── university_campuses (int), sponsored (always 0)
└── confidence_score, validation_status, review_status

ExtractedProgram (actual major)
├── program_name: "B.Tech Computer Science" (real degree, NOT faculty name)
├── degree_level: bachelor | master | phd | diploma | professional
├── field_of_study: "Engineering" (discipline)
├── faculty_or_school: "School of Engineering" (organizational unit)
├── duration, tuition_fee, program_url
└── source_url: official website

ExtractedSpecialization (sub-track)
├── specialization_name: "AI/ML", "Cybersecurity"
└── linked to ExtractedProgram
```

### Multi-Source Architecture

```
Source Priority (University fields):
1. Official Website (multi-page: Contact, Student Life, About, Admissions)
2. Wikipedia Infobox (basic metadata)
3. QS Rankings (global_rank, student stats)
4. AI Enrichment (Fanar → Gemini fallback)

Source Priority (Programs/Majors):
1. Official Website (degree keyword detection)
2. Wikipedia Sections (supplement, filtered for real programs)
3. AI (always runs for universities with < 5 programs)
```

---

## 3. Directory Structure

```
beyond_degree/
├── config/                    # Django settings
│   └── settings.py           # DB, API keys, ETL config
├── academic_etl/             # ETL pipeline app (staging)
│   ├── models.py             # ExtractedUniversity, ExtractedProgram, ExtractedSpecialization
│   ├── views.py              # Pipeline orchestration, dashboard, API endpoints
│   ├── urls.py               # URL routing
│   ├── admin.py              # Django admin registration
│   ├── templates/            # HTML templates (dashboard, run detail, lists)
│   └── services/             # Business logic modules
│       ├── pipeline.py           # Core pipeline: crawl_run, enrich_from_wikipedia
│       ├── discovery.py          # University discovery (Wikipedia + Wikidata)
│       ├── multi_source_scraper.py # Multi-page website scraper
│       ├── extraction.py         # HTML → program extraction rules
│       ├── wikipedia_extract.py  # Wikipedia article parsing
│       ├── fanar_enrich.py       # Fanar AI enrichment (6-model round-robin)
│       ├── gemini_enrich.py      # Google Gemini grounded enrichment
│       ├── llm_provider.py       # Unified LLM with Fanar→Gemini fallback
│       ├── validation.py         # Data validation + auto-approve
│       ├── normalize.py          # Phone/email/URL normalization
│       ├── financial.py          # Financial format standardization
│       ├── country_registry.py   # 31 countries config (currency, languages)
│       ├── classification.py     # Institution type classification
│       ├── exporter.py           # CSV export (22-column format)
│       ├── importer.py           # Import approved data → production
│       ├── crawler.py            # SiteCrawler with HTTP/HTTPS fallback
│       └── lang.py               # English language detection
├── universities/             # Production app
│   └── models.py             # University, Program, Specialization (clean data)
├── sample_data/              # Sample CSV files
├── sample_output/            # Example export files
├── var/                      # Runtime data (caches, logs)
│   ├── html_cache/           # Cached HTML pages
│   ├── fanar_cache/          # Cached Fanar API responses
│   └── gemini_cache/         # Cached Gemini API responses
├── .env                      # API keys (git-ignored)
├── .env.example              # Template for .env
├── requirements.txt          # Python dependencies
├── manage.py                 # Django management
└── db.sqlite3                # SQLite database
```

---

## 4. API Integration

### Fanar API (Primary AI Provider)
- **Base URL**: `https://api.fanar.qa/v1`
- **Auth**: Bearer token (FANAR_API_KEY)
- **Rate limit**: 50 req/min per model × 6 models = **300 req/min effective**
- **Models**: Fanar-C-2-27B, Fanar-Sadiq, Fanar-Sadiq-Agentic, Fanar-C-1-8.7B, Fanar-S-1-7B, Fanar
- **Use cases**: University field enrichment, majors extraction

### Google Gemini (Fallback + Grounded Search)
- **SDK**: `google-genai`
- **Feature**: Google Search grounding — answers verified against live search results
- **Rate limit**: Daily free quota per key per model
- **Models**: gemini-2.5-flash (default), gemini-2.5-flash-lite, gemini-2.0-flash

---

## 5. Key Features

### Dashboard
- Start pipeline run (select Country, Mode: Fast/Thorough)
- Real-time progress tracking (6 steps with percentage)
- Chart.js charts: validation funnel, completeness, field coverage
- LLM provider status indicator

### Data Quality
- Phone: E.164 format only (+91XXXXXXXXXX), rejects dates/years
- Email: RFC-compliant validation
- Campus life: English only, 2-3 sentences minimum (AI rewrites non-English)
- Financials: "CURRENCY low-high ($USD_low-USD_high)" format
- Smart dedup: same name + same city = duplicate; same name + different city = keep both
- Auto-approve: all critical fields filled + confidence >= 0.5

### Global Workspace
- Cross-run university list with search/filter
- Cross-run majors list with search/filter
- CSV export (universities 22-col, majors simple 3-col)

---

## 6. Current Results

| Metric | Value |
|--------|-------|
| Countries supported | 31 (registry) |
| India run | 242 universities discovered |
| Programs per university | 15-50 (target via AI) |
| Data completeness | name 100%, website 98%, description 100% |
| Phone capture rate | ~45% (multi-page scraper) |
| Email capture rate | ~47% |
| Auto-approve rate | ~95% |
