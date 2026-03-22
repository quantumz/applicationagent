# ApplicationAgent Scrapers

Automated job scraping and batch analysis for personal job search.

## What This Does

**End-to-end workflow:**
1. Scraper pulls jobs from job boards based on your search criteria
2. Batch analyzer runs them all through ApplicationAgent
3. You get a ranked list: "Apply to these 5, skip these 15"

**Design philosophy:**
- Quiet, human-paced requests (3-8 second delays)
- One IP, one account (just a person looking for work)
- Respectful rate limiting (50 jobs max per run)
- Invisible in the crowd

---

## Built-in Scraper: Hybrid Scraper

The hybrid scraper is a human-in-the-loop browser scraper. You solve any CAPTCHA or Cloudflare challenge manually — automation handles everything else.

**How it works:**
1. Opens a real browser window (Playwright/Chromium)
2. If a challenge appears, you solve it in the window
3. Once past the challenge, the scraper clicks through job listings automatically
4. Results saved to `data/scraped/hybrid_scraper_{resume_type}_{date}.json`

### Running from the UI

Click **Run** → **Full Pipeline** (or **Scrape Only**) in the web interface. The UI launches the scraper and streams live output.

### Running from the CLI

```bash
python applicationagent.py my_resume --scrape-only
```

Or specify a scraper explicitly:
```bash
python applicationagent.py my_resume --scraper hybrid_scraper
```

---

## Configuration

### Search Queries (per resume)

Edit `resumes/<name>/<name>_search_criteria.json`:

```json
{
  "search_queries": [
    {
      "keywords": "DevOps Engineer",
      "location": "Portland OR",
      "max_results": 15
    },
    {
      "keywords": "Site Reliability Engineer",
      "location": "Remote",
      "max_results": 15
    }
  ],
  "exclude_keywords": [
    "Junior",
    "Clearance Required"
  ],
  "location_preferences": ["Portland", "Oregon", "Remote"]
}
```

### Exclude Keywords

Skip jobs containing these terms:

```json
"exclude_keywords": [
  "Junior",
  "Entry Level",
  "Clearance Required",
  "Secret Clearance",
  "Relocation Required"
]
```

### Rate Limiting (global)

Edit `scrapers/scraper_config.json`:

```json
"rate_limiting": {
  "min_delay_seconds": 3,
  "max_delay_seconds": 8,
  "max_jobs_per_run": 50,
  "max_jobs_per_query": 20
}
```

**Why this matters:**
- Looks human (random timing)
- Avoids detection/blocking
- Respectful of servers

### Browser Config

```json
"browser_config": {
  "headless": false,
  "viewport": { "width": 1920, "height": 1080 }
}
```

Set `"headless": false` to watch it work (useful for debugging). Required for the human-in-the-loop Cloudflare solving.

---

## Output Format

Scraper output is saved to `data/scraped/`:

```
data/
├── applicationagent.db
└── scraped/
    └── hybrid_scraper_my_resume_2026-03-13.json
```

Structure:

```json
{
  "scraped_at": "2026-03-13T09:30:00",
  "source":     "hybrid_scraper",
  "resume_type": "my_resume",
  "total_jobs": 23,
  "jobs": [
    {
      "id":          "abc123",
      "title":       "Senior Platform Engineer",
      "company":     "Acme Corp",
      "location":    "Portland, OR",
      "salary":      "$150K-$190K",
      "url":         "https://example.com/jobs/abc123",
      "description": "Full job description text...",
      "scraped_at":  "2026-03-13T09:32:15",
      "search_query": "DevOps Engineer Portland OR"
    }
  ]
}
```

The `source` field is stored in the database and shown in the UI so you know which scraper found each job.

---

## Plugin System

You can add your own scrapers by dropping a `.py` file into `scrapers/plugins/`.

The `plugins/` directory is gitignored — your scrapers stay local and are never committed to the repo.

See **`scrapers/plugins/README.md`** for the full authoring guide and a working template.

> **Terms of Service:** Scraping behavior and ToS compliance is entirely the plugin author's responsibility. ApplicationAgent provides the interface — you own what your plugin does.

---

## Troubleshooting

**Scraper finds no jobs:**
- Check your search keywords (try broader terms)
- Verify location is formatted correctly
- Set `"headless": false` to see what's happening in the browser

**Scraper is blocked / CAPTCHA:**
- The hybrid scraper handles this — it pauses and waits for you to solve it manually
- If it keeps happening, increase delays in `scraper_config.json`
- Wait a few hours and try again

**Analysis fails:**
- Check your Anthropic API key — open the ⚙ Settings button in the UI
- Verify job descriptions aren't empty in the output JSON
- Check for API rate limits (you'll see errors in the log stream)

**Jobs are all SKIP:**
- Your keywords might be too specific — try broader search terms
- Check `exclude_keywords` — might be filtering out good jobs
- Check `location_preferences` — might be filtering out compatible locations

---

## Best Practices

**How often to run:**
- Once per day max
- Preferably 2-3 times per week
- Don't spam job boards — you'll get blocked

**How many jobs:**
- Start with 10-20 to test your setup
- Scale up to 50 max per run
- More than 50 looks like a bot

**What to exclude:**
- Keywords you absolutely won't accept
- Keep the list short (5-10 max)
- Too many exclusions = missing good jobs

---

## Example Workflow

**Monday morning:**
```bash
# Full pipeline via CLI
python applicationagent.py my_resume

# Or scrape now, analyze later
python applicationagent.py my_resume --scrape-only
# Output: data/hybrid_scraper_my_resume_2026-03-13.json

python applicationagent.py my_resume --analyze-only data/scraped/hybrid_scraper_my_resume_2026-03-13.json
```

**Results show:**
```
3 STRONG_MATCH
8 APPLY
12 SKIP
```

Apply to the STRONG_MATCHes today. Work through the APPLY list this week. Skip the rest.

**Don't apply to everything.** Quality over quantity.

---

## Security Notes

**What gets scraped:**
- Publicly visible job postings
- Same data you'd see browsing manually
- No login required, no personal data accessed

**Your privacy:**
- Scraper runs locally on your machine
- No data sent anywhere except Anthropic API (for analysis)
- Jobs saved locally in `data/`
