# Commitment Checklist - Beyond Degree

**Meeting**: Sunday, 7:00 PM
**Project**: Beyond Degree - Global University Data ETL Pipeline

---

## 1. Project Description Document

| Item | Status | File |
|------|--------|------|
| Project overview | Done | `docs/PROJECT_DESCRIPTION.md` |
| 6-step pipeline architecture | Done | `docs/PROJECT_DESCRIPTION.md` → Section 2 |
| Data model (3-level hierarchy) | Done | `docs/PROJECT_DESCRIPTION.md` → Section 2 |
| Directory structure | Done | `docs/PROJECT_DESCRIPTION.md` → Section 3 |
| API integration (Fanar + Gemini) | Done | `docs/PROJECT_DESCRIPTION.md` → Section 4 |
| Key features | Done | `docs/PROJECT_DESCRIPTION.md` → Section 5 |

---

## 2. Data

| Item | Status | Details |
|------|--------|---------|
| Database (SQLite) | Available | `db.sqlite3` |
| Sample data India | 242 universities | Pipeline run #1 |
| Sample CSV output | Available | `sample_output/` |
| Sample input CSV | Available | `sample_data/` |
| 22-column university format | Defined | Exporter: id, name, location, description, slug, sponsored, website, global_rank, financials, student_loan_available, campus_student_life, number_of_students, student_to_faculty_ratio, international_student_ratio, housing_availability, admissions_contact, admissions_phone, contact_person, admissions_page_link, immigration_support, university_campuses |

---

## 3. Source Code

| Module | Status | Description |
|--------|--------|-------------|
| `config/settings.py` | Done | Django settings + ETL config |
| `academic_etl/models.py` | Done | 10+ models (PipelineRun, ExtractedUniversity, ExtractedProgram, ExtractedSpecialization, etc.) |
| `academic_etl/views.py` | Done | Pipeline orchestration, dashboard, CRUD, export |
| `academic_etl/services/` | Done | 20+ service modules |
| `academic_etl/templates/` | Done | Dashboard, run detail, university list, majors list |
| `universities/models.py` | Done | Production models (University, Program) |
| `requirements.txt` | Done | 4 dependencies |
| `.env.example` | Done | API key template |

---

## 4. Setup Guide

| Item | Status | File |
|------|--------|------|
| System requirements | Done | `docs/SETUP_GUIDE.md` |
| Step-by-step installation | Done | `docs/SETUP_GUIDE.md` |
| API key configuration | Done | `docs/SETUP_GUIDE.md` |
| Usage instructions | Done | `docs/SETUP_GUIDE.md` |
| Troubleshooting | Done | `docs/SETUP_GUIDE.md` |

---

## 5. Progress Summary

### Completed
- [x] 6-step ETL pipeline architecture (discover → crawl → programs → AI fields → AI majors → validate)
- [x] Multi-source discovery: Wikipedia + Wikidata + UniRank
- [x] Multi-page web scraper: Homepage + Contact + Student Life + Admissions + About
- [x] Fanar AI integration: 6-model round-robin (300 req/min)
- [x] Gemini AI integration: Google Search grounding + fallback
- [x] Phone normalization: E.164 format, reject dates/years
- [x] Financial format: "INR 50k-200k ($600-2400)" with USD conversion
- [x] Smart dedup: name + city disambiguation
- [x] Auto-approve: critical fields + confidence >= 0.5
- [x] Dashboard UI: Chart.js charts, real-time progress, data management
- [x] CSV export: 22-column university format, 3-column majors format
- [x] 3-level majors hierarchy: field_of_study → program_name → specializations
- [x] Country-aware AI prompts (India, Vietnam degree naming conventions)
- [x] Non-English content detection + AI rewrite to English

### In Progress
- [ ] Optimize pipeline for multiple countries (currently tested mainly with India)
- [ ] Increase financial data coverage (current ~18% → target >50%)
- [ ] Global rank coverage (current ~2% → target >10%)
- [ ] Entity resolution (ROR ID) for cross-run deduplication

---

## Deliverables File List

```
docs/
├── PROJECT_DESCRIPTION.md    ← Project description document
├── SETUP_GUIDE.md            ← Installation guide
└── CHECKLIST.md              ← This file (commitment checklist)

Source code:
├── academic_etl/             ← ETL pipeline (main app)
├── universities/             ← Production models
├── config/                   ← Django settings
├── requirements.txt          ← Dependencies
├── .env.example              ← API key template
└── manage.py                 ← Entry point

Data:
├── db.sqlite3                ← Database with India sample data
├── sample_data/              ← Sample CSV input
└── sample_output/            ← Sample CSV output
```
