# ApplicationAgent

**Your personal job screening agent** — don't waste time applying to jobs that will auto-reject you.

## What It Does

Instead of companies screening you, **this screens jobs for you.**

```
Input: Job description + your resume
Output: Decision + detailed analysis + PDF report
```

**Analyzes:**
- Keyword match — do you have the skills they want?
- Experience level — over/under/right fit?
- ATS compatibility — will automated screening pass you?
- Role fit — does your background actually match the role?
- Competitive strengths and gaps
- Interview process signals (red flags in the JD)
- Application strategy

**Decisions:**
| Decision | Meaning | Score |
|---|---|---|
| `STRONG_MATCH` | Apply immediately | ≥ 0.90 |
| `APPLY` | Good fit, worth applying | ≥ 0.70 |
| `ATS_ONLY` | Passes automated screening, human will likely reject (role fit gap) | ≥ 0.70, POOR role fit |
| `MAYBE` | Mediocre match, apply if volume is low | ≥ 0.50 |
| `SKIP` | Don't waste time | < 0.50 |
| `CONSIDER` | Manual override — you've decided to apply regardless of score | Human-assigned |

**Role Fit Gate:** POOR role fit caps score at 0.65 (below APPLY threshold). FAIR role fit caps at 0.65. GOOD/EXCELLENT: no cap.

---

## Quick Start

```bash
bash install.sh
```

The installer handles everything: Python packages, Chromium browser driver, and (on Linux) a single-click desktop launcher in your applications menu.

After install, open the app, enter your Anthropic API key (get one free at https://console.anthropic.com), upload your resume, and start screening jobs.

**That's it. Everything else is done from the UI.**

See [`docs/getting-started.md`](docs/getting-started.md) for step-by-step instructions.

---

## Using the UI

The web UI is the primary interface. You do not need to use the command line after initial setup.

**From the browser at http://localhost:8080 you can:**

- **Run the full pipeline** — scrape job boards → AI analysis → track results. Click "Run" and watch live output stream to the screen.
- **Manually analyze a job** — paste any job description and get an instant AI score, decision, and reasoning PDF. No scraping required.
- **View and filter results** — filterable table by decision category (STRONG_MATCH, APPLY, MAYBE, SKIP, CONSIDER, ATS_ONLY) or by search query.
- **Open reasoning reports** — every job has a PDF with full AI reasoning. Click the link in the Reasoning column.
- **Override decisions** — use the Consider button on any SKIP or ATS_ONLY row to manually flag a job regardless of score. The algorithm advises, you decide.
- **Track applications** — mark jobs as applied directly in the table.
- **Re-analyze** — re-run AI scoring on existing jobs when you update your resume or tune the scoring logic. No re-scraping, no repeat API cost for scraping.

**`applicationagent.py` is the engine. The UI drives it. You don't need to run it directly.**

---

## CLI Usage (Advanced)

The CLI is available for scripting, automation, or if you prefer the terminal. Most users should use the web UI instead.

**Full pipeline (scrape → analyze → track):**
```bash
python applicationagent.py my_resume
```

**Scrape only:**
```bash
python applicationagent.py my_resume --scrape-only
```

**Analyze an existing data file (skip scraping):**
```bash
python applicationagent.py my_resume --analyze-only data/scraped/hybrid_scraper_my_resume_2026-03-08.json
```

**Re-analyze all existing jobs with current scoring logic:**
```bash
python applicationagent.py my_resume --reanalyze
```

**Re-analyze specific jobs by ID:**
```bash
python applicationagent.py my_resume --reanalyze --job-ids 5,12,18
```

**Update spreadsheet only:**
```bash
python applicationagent.py my_resume --track-only
```

**Reset deduplication cache before scraping:**
```bash
python applicationagent.py my_resume --reset-cache
```

---

## How It Works

**Two-phase analysis:**

**Phase 1: Quick Checks** (instant, no API cost)
- Title match
- Seniority level alignment
- Location compatibility
- Obvious dealbreakers (clearance required, relocation, etc.)

**Phase 2: AI Analysis** (Anthropic API)
- Semantic keyword matching (context-aware, not word search)
- Experience level fit
- ATS pass likelihood with reasoning
- Role fit assessment with hard gate on scoring
- Competitive strengths and gaps
- Interview process signals
- Application strategy and overall reasoning

Every job gets a PDF report regardless of decision — SKIP jobs include reasoning for why they were skipped.

---

## Project Structure

```
applicationagent_v2/
├── applicationagent.py          # CLI entry point — scrape → analyze → track
├── core/
│   ├── agent.py                 # Fit analysis engine + scoring
│   └── database.py              # SQLite database layer
├── resumes/
│   └── <type>/
│       ├── <type>.txt           # Plain text resume (gitignored)
│       └── <type>_search_criteria.json  # Search queries + location prefs (gitignored)
├── scrapers/
│   ├── hybrid_scraper.py        # ZipRecruiter scraper (Playwright)
│   └── scraper_config.json      # Rate limits, browser config, global exclusions
├── scripts/
│   ├── batch_analyzer.py        # Batch AI analysis + PDF generation
│   └── tracker.py               # Excel spreadsheet generator
├── data/                        # SQLite DB + scraper JSON output (gitignored)
├── output/
│   ├── excel/                   # job_tracker.xlsx (gitignored)
│   └── pdf/                     # Per-job PDF reports (gitignored)
├── ui/
│   ├── app.py                   # Flask web app (primary interface)
│   ├── templates/index.html
│   └── static/
├── tests/
├── requirements.txt
├── .env.sample
└── README.md
```

---

## Configuration

**Search queries and location** (`resumes/<type>/<type>_search_criteria.json`):
```json
{
  "search_queries": [
    {"keywords": "DevOps Engineer", "location": "Portland OR", "max_results": 10},
    {"keywords": "Site Reliability Engineer", "location": "Remote", "max_results": 10}
  ],
  "exclude_keywords": ["Junior", "Intern"],
  "location_preferences": ["Portland", "Oregon", "Remote"]
}
```

**Rate limits and browser config** (`scrapers/scraper_config.json`) — global, applies to all resume types.

---

## Cost

- Quick checks: free
- AI analysis: ~$0.003–0.006 per job (claude-sonnet)
- 50 jobs: ~$0.25
- 100 jobs: ~$0.50
