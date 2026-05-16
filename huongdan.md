# Huong dan chay local

Project hien tai khong con du lieu mau fallback o frontend. Muon xem dashboard, create job, templates, activity hoac job detail thi backend phai chay va API phai tra du lieu that tu database/source catalog.

## 1. Chay bang Docker Compose

Chay o root project:

```powershell
docker compose up --build
```

Dia chi chinh:

- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- Backend health: http://localhost:8000/api/v1/health
- n8n: http://localhost:5678
- Postgres: localhost:5432

Neu dung AI/live crawl, set secret that truoc khi chay:

- `GEMINI_API_KEY`
- `WIKIDATA_CONTACT_EMAIL` neu crawl Wikidata nhieu lan
- `N8N_WEBHOOK_SECRET` neu dung webhook

## 2. Chay tung service

Terminal 1:

```powershell
cd "D:\work\New folder\beyond2\backend"
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
cd "D:\work\New folder\beyond2\frontend"
npm install
npm run dev
```

Mo frontend:

- http://localhost:3000

## 3. Neu frontend bao fetch failed

Kiem tra backend:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

Neu backend chua chay hoac Postgres chua san sang, frontend se bao loi live-data thay vi hien du lieu mau.

## 4. Chay test

Unit/integration test mac dinh khong hit web that:

```powershell
cd "D:\work\New folder\beyond2\backend"
pytest
```

Live web-source test se crawl web that va can bat bien moi truong:

```powershell
cd "D:\work\New folder\beyond2\backend"
$env:RUN_LIVE_WEB_TESTS="true"
pytest tests/test_live_discovery_sources.py
```

Neu live test fail, can phan biet ro la do adapter logic hay do web/network/rate-limit thay doi.
