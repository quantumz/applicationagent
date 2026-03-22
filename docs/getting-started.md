# ApplicationAgent — Getting Started

ApplicationAgent screens job postings **before** you apply, so you stop wasting time on applications that will auto-reject you.

---

## Installation

Open a terminal in the folder where you extracted ApplicationAgent and run:

```bash
bash install.sh
```

The installer will ask you two questions:

1. **Desktop or CLI?** — Choose Desktop unless you know you want CLI.
2. **Virtual environment path** (CLI only) — Press Enter to use the default.

That's it. The installer handles Python packages, the browser driver, and the desktop launcher automatically.

---

## First Launch

**Desktop install:** Press the Super key (⊞ Windows key), search for **ApplicationAgent**, and click it. Your browser will open automatically.

**CLI install:** Run `applicationagent-ui` in a terminal, then open **http://localhost:8080** in your browser.

---

## Step 1 — Add Your API Key

The first time you open the app, you'll see a prompt for your Anthropic API key.

**To get a free API key:**

1. Go to **https://console.anthropic.com**
2. Sign up (or log in)
3. Click **API Keys** in the left menu
4. Click **Create Key**, give it a name (anything), click **Create**
5. Copy the key — it starts with `sk-ant-...`
6. Paste it into the ApplicationAgent prompt and click **Save**

The key is stored locally on your machine. It is never sent anywhere except directly to Anthropic's API when you analyze a job.

> **Cost:** Each job analysis costs roughly $0.003–$0.006. Analyzing 50 jobs costs about $0.25.

---

## Step 2 — Add Your Resume

Click **+ Resume** in the top bar.

- Give it a short name with no spaces (e.g. `my_resume`, `marketing`, `manager`)
- Upload your resume as a `.txt` or `.pdf` file
- Add at least one **search query**: the job title to search for, and a location (or "Remote")
- Click **Upload**

Your resume will appear in the dropdown next to **Run**.

> **Tip:** Plain text resumes work best. If you upload a PDF, the app extracts the text automatically — check it looks right before running a batch analysis.

---

## Step 3 — Analyze a Single Job (Fastest Way to Start)

Click **Analyze Job**.

- Paste the job title, company name, and the full job description
- Optionally paste the job URL — the company name becomes a clickable link
- Select your resume from the dropdown
- Click **Analyze**

Results appear immediately. The job is saved and added to the main table.

---

## Step 4 — Scrape + Analyze in Bulk

Click **Run**, then choose a mode:

| Mode | What It Does |
|------|-------------|
| Full Pipeline | Scrape job boards → AI analysis → update spreadsheet |
| Scrape Only | Collect jobs, stop before AI analysis |
| Analyze Only | Run AI on an existing scraped file |
| Track Only | Update the Excel spreadsheet from existing results |

**Reset Cache** — check this if you want to re-scrape jobs you've already seen.

The log window streams live output so you can watch progress.

---

## Reading the Results

The results table shows all analyzed jobs for the selected resume.

| Column | Meaning |
|--------|---------|
| Applied | Check this when you apply — the row shows a green strikethrough |
| Decision | See decision meanings below |
| Score | 0.0 (terrible fit) → 1.0 (perfect fit) |
| ATS | Will automated keyword screening pass you? HIGH / MEDIUM / LOW |
| Reasoning | Link to the full PDF report — generated for every job |

### What the Decisions Mean

| Decision | Meaning | Score |
|----------|---------|-------|
| **STRONG_MATCH** | Apply immediately. You're a strong fit on all dimensions. | ≥ 0.90 |
| **APPLY** | Good fit. Worth your time. | ≥ 0.70 |
| **ATS_ONLY** | Your keywords pass automated screening, but a human reviewer will likely reject due to a role fit gap. Apply only if making a deliberate stretch attempt. | ≥ 0.70, POOR role fit |
| **MAYBE** | Borderline. Read the reasoning before deciding. | ≥ 0.50 |
| **SKIP** | Don't bother. Here's why. | < 0.50 |
| **CONSIDER** | You manually flagged this job to apply regardless of score. | Human-assigned |

### The Consider Button

On any **SKIP** or **ATS_ONLY** row, you'll see a **Consider** button. Click it to override the AI's decision — useful when you know something about the company or role that the algorithm can't see. The decision changes to **CONSIDER** and is preserved even if you re-analyze.

---

## Re-Analyze

If you update your resume or the scoring logic changes, click **Re-Analyze** to re-run AI scoring on all existing jobs without re-scraping. No additional scraping cost.

---

## Files

Your resume and search settings live in `resumes/<name>/` inside the install directory:

```
resumes/
└── my_resume/
    ├── my_resume.txt                   ← your resume (plain text)
    └── my_resume_search_criteria.json  ← what to search for
```

PDF reports go to `output/pdf/`. The Excel tracker goes to `output/excel/`.

---

## Tips

- **The AI reads your resume the same way ATS does.** If a keyword isn't in your resume text, it's not there as far as the tool is concerned.
- **Location preferences** in your search criteria control what counts as a compatible location. Add `"remote"` to the list if you want remote jobs to pass the location check.
- **Interview red flags** are automatically flagged — things like 6-round interview loops, unpaid take-homes, or LeetCode for senior roles.
- **Every job gets a PDF** — even SKIPs include the reasoning, so you can see exactly why a job was dismissed.
