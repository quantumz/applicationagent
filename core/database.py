"""
ApplicationAgent - SQLite Database
Single source of truth for jobs, analysis, and applied state.
"""

import json
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'applicationagent.db'


def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA journal_mode = WAL')
    return conn


def init_db():
    """Create schema if not exists. Safe to call multiple times."""
    with get_db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS jobs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                resume_type TEXT NOT NULL,
                source      TEXT NOT NULL DEFAULT 'hybrid_scraper',
                title       TEXT NOT NULL,
                company     TEXT NOT NULL,
                location    TEXT,
                salary      TEXT,
                url         TEXT NOT NULL DEFAULT '',
                description TEXT,
                scraped_at  TEXT,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_url
                ON jobs(url, resume_type) WHERE url != '';

            CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_nurl
                ON jobs(title, company, resume_type) WHERE url = '';

            CREATE TABLE IF NOT EXISTS analysis (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id      INTEGER NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
                decision    TEXT,
                fit_score   REAL,
                quick_checks TEXT,
                ai_analysis  TEXT,
                analyzed_at  TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS applied_jobs (
                job_id     INTEGER PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
                applied_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS resumes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT UNIQUE NOT NULL,
                file_path  TEXT NOT NULL,
                search_criteria TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS settings (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            );
        ''')
        # ALTER TABLE doesn't support IF NOT EXISTS — check first
        existing_cols = {row[1] for row in conn.execute('PRAGMA table_info(jobs)')}
        if 'resume_id' not in existing_cols:
            conn.execute('ALTER TABLE jobs ADD COLUMN resume_id INTEGER REFERENCES resumes(id)')
        if 'search_query' not in existing_cols:
            conn.execute('ALTER TABLE jobs ADD COLUMN search_query TEXT')
        if 'override' not in existing_cols:
            conn.execute('ALTER TABLE jobs ADD COLUMN override BOOLEAN DEFAULT FALSE')
        if 'override_at' not in existing_cols:
            conn.execute('ALTER TABLE jobs ADD COLUMN override_at TIMESTAMP DEFAULT NULL')
        if 'override_from_score' not in existing_cols:
            conn.execute('ALTER TABLE jobs ADD COLUMN override_from_score REAL DEFAULT NULL')
        if 'override_note' not in existing_cols:
            conn.execute('ALTER TABLE jobs ADD COLUMN override_note TEXT DEFAULT NULL')
        if 'pipeorgan_job_id' not in existing_cols:
            conn.execute('ALTER TABLE jobs ADD COLUMN pipeorgan_job_id TEXT DEFAULT NULL')
        if 'forge_status' not in existing_cols:
            conn.execute('ALTER TABLE jobs ADD COLUMN forge_status TEXT DEFAULT NULL')


def upsert_job(resume_type, source, title, company, location, salary, url,
               description, scraped_at, search_query=''):
    """Insert job, return its ID. On conflict returns the existing row's ID."""
    url = url or ''
    with get_db() as conn:
        try:
            cur = conn.execute(
                '''INSERT INTO jobs
                   (resume_type, source, title, company, location, salary, url, description, scraped_at, search_query)
                   VALUES (?,?,?,?,?,?,?,?,?,?)''',
                (resume_type, source, title, company, location, salary, url, description, scraped_at, search_query or '')
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            if url:
                row = conn.execute(
                    'SELECT id FROM jobs WHERE url=? AND resume_type=?',
                    (url, resume_type)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT id FROM jobs WHERE title=? AND company=? AND resume_type=? AND url=''",
                    (title, company, resume_type)
                ).fetchone()
            existing_id = row['id'] if row else None
            if existing_id and search_query:
                conn.execute(
                    'UPDATE jobs SET search_query=? WHERE id=? AND (search_query IS NULL OR search_query="")',
                    (search_query, existing_id)
                )
            return existing_id


def upsert_analysis(job_id, decision, fit_score, quick_checks, ai_analysis):
    """Insert or overwrite analysis for a job. Does not overwrite CONSIDER override."""
    with get_db() as conn:
        # Check if job has a CONSIDER override — preserve it
        override_row = conn.execute(
            'SELECT override FROM jobs WHERE id = ?', (job_id,)
        ).fetchone()
        is_override = override_row and override_row['override']

        conn.execute(
            '''INSERT INTO analysis (job_id, decision, fit_score, quick_checks, ai_analysis)
               VALUES (?,?,?,?,?)
               ON CONFLICT(job_id) DO UPDATE SET
                   decision=CASE WHEN (SELECT override FROM jobs WHERE id=excluded.job_id) THEN decision ELSE excluded.decision END,
                   fit_score=excluded.fit_score,
                   quick_checks=excluded.quick_checks,
                   ai_analysis=excluded.ai_analysis,
                   analyzed_at=CURRENT_TIMESTAMP''',
            (job_id, decision, float(fit_score or 0),
             json.dumps(quick_checks), json.dumps(ai_analysis))
        )


def get_results(resume_type=None):
    """Return all analyzed jobs as dicts matching the legacy API shape."""
    with get_db() as conn:
        query = '''
            SELECT j.id, j.resume_type, j.source, j.title, j.company,
                   j.location, j.salary, j.url, j.scraped_at, j.search_query,
                   j.override, j.override_from_score,
                   a.decision, a.fit_score, a.quick_checks, a.ai_analysis,
                   (ap.job_id IS NOT NULL) AS applied
            FROM jobs j
            JOIN analysis a ON a.job_id = j.id
            LEFT JOIN applied_jobs ap ON ap.job_id = j.id
        '''
        params = ()
        if resume_type:
            query += ' WHERE j.resume_type = ?'
            params = (resume_type,)
        query += ' ORDER BY a.fit_score DESC, j.created_at DESC'
        rows = conn.execute(query, params).fetchall()

    results = []
    for row in rows:
        results.append({
            'id': row['id'],
            'decision': row['decision'],
            'fit_score': row['fit_score'],
            'applied': bool(row['applied']),
            'override': bool(row['override']),
            'override_from_score': row['override_from_score'],
            'resume_type': row['resume_type'],
            'quick_analysis': json.loads(row['quick_checks'] or '{}'),
            'ai_analysis': json.loads(row['ai_analysis'] or '{}'),
            'job_metadata': {
                'title': row['title'],
                'company': row['company'],
                'location': row['location'] or '',
                'salary': row['salary'] or '',
                'url': row['url'] or '',
                'scraped_at': row['scraped_at'] or '',
                'search_query': row['search_query'] or '',
            }
        })
    return results


def set_consider(job_id, current_score):
    """Mark a job as CONSIDER (manual override). Preserves override_at/score on re-call."""
    with get_db() as conn:
        # Update decision in analysis table
        conn.execute(
            '''UPDATE analysis SET decision='CONSIDER' WHERE job_id=?''',
            (job_id,)
        )
        # Set override columns — only write override_at/score if not already set
        conn.execute(
            '''UPDATE jobs SET
                   override=TRUE,
                   override_at=COALESCE(override_at, datetime('now')),
                   override_from_score=COALESCE(override_from_score, ?)
               WHERE id=?''',
            (current_score, job_id)
        )


def delete_job(job_id):
    """Delete a job and all related records via cascade."""
    with get_db() as conn:
        conn.execute('DELETE FROM jobs WHERE id = ?', (job_id,))


def set_applied(job_id, applied: bool):
    with get_db() as conn:
        if applied:
            conn.execute(
                'INSERT OR IGNORE INTO applied_jobs (job_id) VALUES (?)', (job_id,)
            )
        else:
            conn.execute('DELETE FROM applied_jobs WHERE job_id = ?', (job_id,))


def import_from_json(data_dir):
    """
    One-time migration: import existing analyzed_*.json files into DB.
    Skips if DB already has data.
    """
    with get_db() as conn:
        count = conn.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]
    if count > 0:
        return 0

    data_dir = Path(data_dir)
    imported = 0
    for f in sorted(data_dir.glob('analyzed_*.json')):
        try:
            with open(f) as fp:
                results = json.load(fp)
            if not isinstance(results, list):
                continue
            # Extract scraper name from filename: analyzed_{source}_{resume_type}_{date}.json
            # Fall back to 'hybrid_scraper' for legacy files named analyzed_ziprecruiter_*.json
            stem_parts = f.stem.replace('analyzed_', '', 1).split('_')
            raw_source = stem_parts[0] if stem_parts else 'hybrid_scraper'
            source = 'manual' if raw_source == 'manual' else (
                'hybrid_scraper' if raw_source == 'ziprecruiter' else raw_source
            )
            for r in results:
                job = r.get('job_metadata', {})
                resume_type = r.get('resume_type', 'unknown')
                job_id = upsert_job(
                    resume_type=resume_type,
                    source=source,
                    title=job.get('title') or 'Unknown',
                    company=job.get('company') or 'Unknown',
                    location=job.get('location') or '',
                    salary=job.get('salary') or '',
                    url=job.get('url') or '',
                    description='',
                    scraped_at=job.get('scraped_at') or '',
                )
                if job_id:
                    upsert_analysis(
                        job_id=job_id,
                        decision=r.get('decision', ''),
                        fit_score=r.get('fit_score', 0),
                        quick_checks=r.get('quick_analysis', {}),
                        ai_analysis=r.get('ai_analysis', {}),
                    )
                    imported += 1
        except Exception as e:
            print(f'  DB import error {f.name}: {e}')
    return imported


def upsert_resume(name, file_path, search_criteria):
    """Insert or update a resume record. Returns the resume ID."""
    with get_db() as conn:
        try:
            cur = conn.execute(
                '''INSERT INTO resumes (name, file_path, search_criteria)
                   VALUES (?, ?, ?)''',
                (name, str(file_path),
                 json.dumps(search_criteria) if search_criteria is not None else None)
            )
            resume_id = cur.lastrowid
        except sqlite3.IntegrityError:
            conn.execute(
                '''UPDATE resumes
                   SET file_path=?, search_criteria=?, updated_at=CURRENT_TIMESTAMP
                   WHERE name=?''',
                (str(file_path),
                 json.dumps(search_criteria) if search_criteria is not None else None,
                 name)
            )
            resume_id = conn.execute(
                'SELECT id FROM resumes WHERE name=?', (name,)
            ).fetchone()['id']
        # Backfill resume_id on jobs that match by resume_type
        conn.execute(
            'UPDATE jobs SET resume_id=? WHERE resume_type=? AND resume_id IS NULL',
            (resume_id, name)
        )
    return resume_id


def migrate_resumes_from_fs(project_root):
    """
    Scan resumes/ directory and populate the resumes table.
    Safe to call multiple times (upsert). Returns count registered.
    """
    resumes_dir = Path(project_root) / 'resumes'
    if not resumes_dir.exists():
        return 0
    count = 0
    for d in sorted(resumes_dir.iterdir()):
        if not d.is_dir() or d.name.startswith('.'):
            continue
        resume_file = d / f'{d.name}.txt'
        criteria_file = d / f'{d.name}_search_criteria.json'
        if not resume_file.exists():
            continue
        search_criteria = None
        if criteria_file.exists():
            try:
                with open(criteria_file) as f:
                    search_criteria = json.load(f)
            except Exception:
                pass
        upsert_resume(d.name, str(resume_file), search_criteria)
        count += 1
    return count


def get_resumes_list():
    """Return all resume records as dicts."""
    with get_db() as conn:
        rows = conn.execute(
            'SELECT id, name, file_path, search_criteria, updated_at FROM resumes ORDER BY name'
        ).fetchall()
    return [
        {
            'id': row['id'],
            'name': row['name'],
            'file_path': row['file_path'],
            'search_criteria': json.loads(row['search_criteria'] or '{}'),
            'updated_at': row['updated_at'] or '',
        }
        for row in rows
    ]


def get_resume_by_id(resume_id):
    """Return a single resume record dict or None."""
    with get_db() as conn:
        row = conn.execute(
            '''SELECT id, name, file_path, search_criteria, created_at, updated_at
               FROM resumes WHERE id=?''',
            (resume_id,)
        ).fetchone()
    if not row:
        return None
    return {
        'id': row['id'],
        'name': row['name'],
        'file_path': row['file_path'],
        'search_criteria': json.loads(row['search_criteria'] or '{}'),
        'created_at': row['created_at'] or '',
        'updated_at': row['updated_at'] or '',
    }


def update_resume_criteria(resume_id, search_criteria):
    """Update search_criteria for a resume. Returns True if row was found."""
    with get_db() as conn:
        cur = conn.execute(
            '''UPDATE resumes
               SET search_criteria=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?''',
            (json.dumps(search_criteria), resume_id)
        )
    return cur.rowcount > 0


def get_resume_stats(resume_id):
    """Return job counts for a resume_id."""
    with get_db() as conn:
        row = conn.execute(
            '''SELECT
                   COUNT(j.id) AS total_jobs,
                   SUM(CASE WHEN a.decision='STRONG_MATCH' THEN 1 ELSE 0 END) AS strong_matches,
                   COUNT(ap.job_id) AS applications
               FROM jobs j
               LEFT JOIN analysis a ON a.job_id = j.id
               LEFT JOIN applied_jobs ap ON ap.job_id = j.id
               WHERE j.resume_id = ?''',
            (resume_id,)
        ).fetchone()
    return {
        'total_jobs': row['total_jobs'] or 0,
        'strong_matches': row['strong_matches'] or 0,
        'applications': row['applications'] or 0,
    }


def delete_resume_record(resume_id):
    """
    Delete a resume and all associated jobs (by resume_id OR resume_type name).
    Returns count of jobs deleted.
    """
    with get_db() as conn:
        row = conn.execute(
            'SELECT name FROM resumes WHERE id=?', (resume_id,)
        ).fetchone()
        if not row:
            return 0
        resume_name = row['name']
        count = conn.execute(
            'SELECT COUNT(*) FROM jobs WHERE resume_id=? OR resume_type=?',
            (resume_id, resume_name)
        ).fetchone()[0]
        conn.execute(
            'DELETE FROM jobs WHERE resume_id=? OR resume_type=?',
            (resume_id, resume_name)
        )
        conn.execute('DELETE FROM resumes WHERE id=?', (resume_id,))
    return count


def get_resume_queries(resume_id):
    """Return search query strings and their job counts for a resume."""
    with get_db() as conn:
        rows = conn.execute(
            '''SELECT search_query, COUNT(*) as cnt
               FROM jobs
               WHERE resume_id = ? AND search_query IS NOT NULL AND search_query != ''
               GROUP BY search_query
               ORDER BY cnt DESC''',
            (resume_id,)
        ).fetchall()
    return [{'query': row['search_query'], 'count': row['cnt']} for row in rows]


def get_all_jobs_for_resume(resume_type):
    """Return all jobs for a resume type (id, title, company, description, etc.)."""
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM jobs WHERE resume_type = ? ORDER BY id',
            (resume_type,)
        ).fetchall()
    return [dict(row) for row in rows]


def get_job_detail(job_id):
    """Return a single job with its analysis data, or None if not found."""
    with get_db() as conn:
        row = conn.execute(
            '''SELECT j.id, j.resume_type, j.title, j.company, j.description,
                      a.fit_score
               FROM jobs j
               LEFT JOIN analysis a ON a.job_id = j.id
               WHERE j.id = ?''',
            (job_id,)
        ).fetchone()
    if not row:
        return None
    return {
        'id': row['id'],
        'resume_type': row['resume_type'],
        'title': row['title'],
        'company': row['company'],
        'description': row['description'] or '',
        'fit_score': row['fit_score'] or 0.0,
    }


def get_jobs_by_ids(job_ids):
    """Return jobs matching the given list of IDs."""
    if not job_ids:
        return []
    placeholders = ','.join('?' * len(job_ids))
    with get_db() as conn:
        rows = conn.execute(
            f'SELECT * FROM jobs WHERE id IN ({placeholders}) ORDER BY id',
            job_ids
        ).fetchall()
    return [dict(row) for row in rows]


def set_pipeorgan_job_id(job_id, pipeorgan_job_id):
    """Store the PipeOrgan-assigned job ID on an appagent job row."""
    with get_db() as conn:
        conn.execute(
            'UPDATE jobs SET pipeorgan_job_id=? WHERE id=?',
            (pipeorgan_job_id, job_id)
        )


def get_job_by_pipeorgan_id(pipeorgan_job_id):
    """Return {id, title, company, resume_type} for the job matching pipeorgan_job_id, or None."""
    with get_db() as conn:
        row = conn.execute(
            'SELECT id, title, company, resume_type FROM jobs WHERE pipeorgan_job_id=?',
            (pipeorgan_job_id,)
        ).fetchone()
    if not row:
        return None
    return {
        'id': row['id'],
        'title': row['title'],
        'company': row['company'],
        'resume_type': row['resume_type'],
    }


def get_pipeorgan_job_id(job_id):
    """Return the pipeorgan_job_id string for the given appagent job_id, or None."""
    with get_db() as conn:
        row = conn.execute(
            'SELECT pipeorgan_job_id FROM jobs WHERE id = ?', (job_id,)
        ).fetchone()
    if not row:
        return None
    return row['pipeorgan_job_id']


def set_forge_status(pipeorgan_job_id, status):
    """Set forge_status on the job row matching pipeorgan_job_id."""
    with get_db() as conn:
        conn.execute(
            'UPDATE jobs SET forge_status=? WHERE pipeorgan_job_id=?',
            (status, pipeorgan_job_id)
        )

# Add this function to the END of core/database.py
# It replaces the pipeorgan_job_id lookup with a direct job_id lookup

def set_forge_status_by_job_id(job_id, status):
    """Set forge_status on the job row matching job_id directly."""
    with get_db() as conn:
        conn.execute(
            'UPDATE jobs SET forge_status=? WHERE id=?',
            (status, job_id)
        )


def set_forge_status_by_job_id(job_id, status):
    """Set forge_status on the job row matching job_id directly."""
    with get_db() as conn:
        conn.execute(
            'UPDATE jobs SET forge_status=? WHERE id=?',
            (status, job_id)
        )
