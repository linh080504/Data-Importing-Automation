# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

- `frontend/`: Next.js 16 dashboard for crawl-job operations. Implemented source lives under `frontend/src`, not a top-level `app/` directory.
- `backend/`: FastAPI service with SQLAlchemy models, service-layer business logic, and pytest coverage.
- `n8n/`: workflow files mounted into the n8n container.
- `docs/`: product and architecture docs that explain the intended end-to-end data pipeline.
- Sample import/export artifacts live at the repository root (`University_Import_Clean-*.csv`) and are referenced by the product flow.

## Key commands

### Full stack via Docker Compose
- Start all services: `docker compose up --build`
- Start in background: `docker compose up -d --build`
- Stop services: `docker compose down`

Services exposed by compose:
- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- n8n: `http://localhost:5678`
- Postgres: `localhost:5432`

### Frontend (`frontend/`)
- Install deps: `npm install`
- Start dev server: `npm run dev`
- Build: `npm run build`
- Start production build: `npm run start`
- Lint: `npm run lint`

### Backend (`backend/`)
- Create venv: `python -m venv .venv`
- Activate on bash: `source .venv/Scripts/activate`
- Install deps: `pip install -r requirements.txt`
- Run API locally: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
- Run tests: `pytest`
- Run a single test file: `pytest tests/test_export_api.py`
- Run a single test: `pytest tests/test_export_api.py -k <test_name>`
- Apply migrations: `alembic upgrade head`

### Backend environment
- Copy `backend/.env.example` to `backend/.env` and set values as needed.
- Important settings come from `app/core/config.py` and include `DATABASE_URL`, `GEMINI_API_KEY`, `N8N_WEBHOOK_SECRET`, `N8N_CALLBACK_HEADER`, and `INTERNAL_WEBHOOK_ENABLED`.
- The Docker backend command automatically runs migrations before starting Uvicorn.

## Code architecture

### End-to-end system shape
This project is a data-operations workflow for collecting raw source data, extracting a small set of critical fields, validating them, routing low-confidence records to manual review, and exporting/importing cleaned data.

The intended system boundary is:
- Next.js dashboard for operators
- FastAPI backend for CRUD, review, export/import, and orchestration-facing endpoints
- PostgreSQL for raw, clean, audit, and template data
- n8n for scheduled crawling and AI workflow orchestration
- Two-stage AI flow: extractor first, validator/judge second

The docs in `docs/ARCHITECTURE.md`, `docs/N8N_AUTOMATION_FLOW.md`, `docs/API_CONTRACT.md`, and `docs/USER_FLOW.md` are important context when changing behavior across frontend, backend, and n8n together.

### Frontend structure
- The app uses the Next.js App Router under `frontend/src/app`.
- Shared UI components live in `frontend/src/components`.
- Client-side API adapters and response mapping live in `frontend/src/lib/api.ts`.
- Shared UI/domain types live in `frontend/src/lib/types.ts`.
- `frontend/src/lib/mock-data.ts` provides fallback data so the UI can still render when the backend is unavailable.

Important frontend behavior:
- Dashboard and job-detail pages are server components that fetch data through `src/lib/api.ts`.
- `src/lib/api.ts` is the translation layer between backend responses and UI view models; many UI changes belong there, not in page components.
- The UI computes operator-facing analytics/readiness summaries from backend compare/review data, including completeness, quality, merge coverage, and export readiness.
- The dashboard is intentionally written for non-technical operators, with chart/summary-heavy presentation rather than raw API output.

### Backend structure
The FastAPI app is mounted in `backend/app/main.py` and includes all routes under `/api/v1`.

Backend layering is consistent:
- `app/api/`: route modules and HTTP boundary logic
- `app/schemas/`: request/response models
- `app/services/`: business logic and orchestration helpers
- `app/models/`: SQLAlchemy persistence models
- `app/db/`: base metadata and session wiring
- `app/core/config.py`: environment-driven settings

Keep business rules in `services`, not in route handlers.

### Important backend flows
- Template ingestion and field suggestion support the “upload clean sample file -> suggest critical fields” workflow.
- Crawl job APIs drive dashboard status, progress, review queue, compare views, export, import readiness, and direct import.
- Review actions update cleaned data through service-layer logic rather than direct route-level mutation.
- The internal n8n webhook at `backend/app/api/internal.py` validates a shared secret header, checks content type, performs raw-record upsert/change detection, and decides whether AI processing should continue.
- Hash/change detection is a core invariant: unchanged raw records should skip downstream AI work.

### Data model concepts
The important domain split is:
- raw records: source payloads and change detection inputs
- clean records: operator-reviewed/exportable output rows
- AI extraction logs: audit/debug trail for extractor and validator output
- review actions: human-in-the-loop corrections and approvals
- templates/data sources/crawl jobs/import logs: operational metadata

When editing the pipeline, preserve the distinction between raw storage, review state, and final clean/exportable state.

### n8n integration assumptions
The n8n workflow is expected to:
- fetch/crawl external sources
- compute a record hash
- skip unchanged records
- run AI extraction and AI validation as separate steps
- send approved or review-needed payloads back to FastAPI through the internal webhook

The backend webhook logic currently expects JSON requests and a secret header whose name defaults to `X-N8N-Secret`.

## Project-specific instructions

- There is already a nested `frontend/CLAUDE.md`; read it before making frontend changes.
- `frontend/AGENTS.md` is important: this codebase uses a newer Next.js version with breaking changes, so read the relevant guide in `frontend/node_modules/next/dist/docs/` before changing framework-specific behavior.
- Prefer understanding whether a frontend screen is backed by live API data or mock fallback data before changing it. Many pages still degrade gracefully to mock data when the backend is absent.
- For changes that affect job lifecycle semantics, review queue behavior, export readiness, or n8n ingestion, inspect both the backend service logic and the frontend mapping code because the UI derives operator-facing status from backend responses.
- Root-level product docs are partly in Vietnamese; preserve domain meaning when translating concepts into code or UX changes.
