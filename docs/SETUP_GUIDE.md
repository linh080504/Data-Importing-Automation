# Setup Guide - Beyond Degree

## System Requirements

| Requirement | Version |
|-------------|---------|
| Python | 3.11+ (recommended 3.13) |
| pip | latest |
| OS | Windows 10/11, macOS, Linux |
| RAM | 4GB+ (recommended 8GB) |
| Disk | 2GB+ (for cache and database) |

---

## Step 1: Clone source code

```bash
git clone <repository_url>
cd beyond_degree
```

## Step 2: Create virtual environment (recommended)

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

## Step 3: Install dependencies

```bash
pip install -r requirements.txt
```

**Main dependencies:**
- `Django>=5.0` — Web framework
- `requests>=2.31` — HTTP client
- `beautifulsoup4>=4.12` — HTML parsing
- `google-genai>=1.0` — Google Gemini SDK

## Step 4: Configure API keys

```bash
# Copy the example .env file
cp .env.example .env
```

Open `.env` and fill in API keys:

```env
# Required: at least 1 of the 2 API keys
GEMINI_API_KEY=AIzaSy_your_key_here
FANAR_API_KEY=your_fanar_key_here

# Optional: multiple Gemini keys to increase quota
# GEMINI_API_KEYS=AIzaSy_key1,AIzaSy_key2,AIzaSy_key3

# Optional: model fallback chain
# GEMINI_MODEL=gemini-2.5-flash,gemini-2.5-flash-lite,gemini-2.0-flash
```

**Where to get API keys:**
- **Gemini**: https://aistudio.google.com/apikey (free tier, key starts with `AIzaSy...`)
- **Fanar**: https://api.fanar.qa (register an account, get Bearer token)

## Step 5: Initialize database

```bash
python manage.py migrate
```

## Step 6: Create superuser (optional, for Django Admin)

```bash
python manage.py createsuperuser
```

## Step 7: Run the server

```bash
# IMPORTANT: use --noreload so background pipeline threads are not killed
python manage.py runserver --noreload
```

Open browser: **http://127.0.0.1:8000/etl/**

---

## Usage

### Running a pipeline crawl

1. Go to **Dashboard** → http://127.0.0.1:8000/etl/
2. Select **Country** (e.g., India)
3. Select **Mode**:
   - **Fast**: Wikipedia + AI enrichment (~5 min for 200 universities)
   - **Thorough**: Wikipedia + Website crawl + AI (~20 min)
4. Click **Start Run**
5. Pipeline runs automatically through 6 steps, progress updates in real-time

### Viewing results

- **Run Detail**: Click "Open" on a run → view statistics, validation
- **Universities**: Tab "Universities" → search/filter, inline edit
- **Majors**: Tab "Majors" → view programs by university
- **Export CSV**: Click "Export Universities CSV" or "Export Majors CSV"

### Data management

- **Approve**: Click "Approve all valid" for bulk approval
- **Delete run**: Click "Delete" on a run to remove staging data
- **Clear staging**: Dashboard → "Clear staging data"

---

## URL Structure

| URL | Function |
|-----|----------|
| `/etl/` | Main dashboard |
| `/etl/runs/` | Pipeline runs list |
| `/etl/runs/<id>/` | Run detail |
| `/etl/runs/<id>/universities/` | Universities in run |
| `/etl/runs/<id>/majors/` | Programs in run |
| `/etl/universities/` | Global universities (cross-run) |
| `/etl/majors/` | Global majors (cross-run) |
| `/admin/` | Django Admin |

---

## Troubleshooting

### Pipeline stuck / not running
```bash
# Make sure the server is running with --noreload
python manage.py runserver --noreload

# If port is occupied
netstat -ano | findstr :8000
taskkill /PID <pid> /F
```

### Fanar API 422 error
- Default model `Fanar-C-2-27B` works best
- The system automatically round-robins across 6 models if one fails

### Gemini quota exhausted
- Add more API keys to `GEMINI_API_KEYS` (each key = separate quota)
- Add model fallback: `GEMINI_MODEL=gemini-2.5-flash,gemini-2.5-flash-lite`

### Database locked (SQLite)
- Caused by concurrent access — normal when pipeline runs in parallel
- If severe: restart the server
