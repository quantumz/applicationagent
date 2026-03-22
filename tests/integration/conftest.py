"""
Shared fixtures for Flask API integration tests.

Reload strategy:
  _app  (module-scoped) — reloads ui.app ONCE per test file.
                           Suppresses startup side effects via patching the
                           three core.database functions that _startup() calls.
                           Sets PROJECT_ROOT and ENV_PATH to a safe temp dir.

  client (function-scoped) — clears all DB tables and re-seeds before each test.
                              Each test gets a clean, known DB state without
                              paying the cost of a full module reload.

Why not reload per test:
  importlib.reload(ui.app) takes ~250ms. At 38+ tests that's 9+ seconds of
  pure overhead before any test logic runs. Module-scoped reload amortizes
  that cost to once per file.

Why patch the three functions instead of _startup:
  importlib.reload() redefines the entire module, so patch.object on _startup
  won't survive. Patching core.database.init_db, import_from_json, and
  migrate_resumes_from_fs before reload means the 'from core.database import'
  inside _startup binds to the mocks, making _startup() a harmless no-op.
"""

import importlib
import json
from pathlib import Path
from unittest.mock import patch
import pytest

import core.database as db_module


def _clear_db():
    """Truncate all tables so each test starts from a known empty state."""
    import sqlite3
    with sqlite3.connect(str(db_module.DB_PATH)) as conn:
        conn.execute('DELETE FROM analysis')
        conn.execute('DELETE FROM applied_jobs')
        conn.execute('DELETE FROM jobs')
        conn.execute('DELETE FROM resumes')
        conn.commit()


def _seed_db(tmp_path):
    """Insert known resumes, jobs, and analyses into the current temp DB."""
    resume_path = tmp_path / 'resumes' / 'test_resume' / 'test_resume.txt'
    resume_path.parent.mkdir(parents=True, exist_ok=True)
    resume_path.write_text('Senior SRE, 15 years, Kubernetes Terraform AWS.')

    criteria = {
        'search_queries': [
            {'keywords': 'SRE', 'location': 'Portland OR', 'max_results': 10},
        ],
        'exclude_keywords': ['Junior'],
        'location_preferences': ['Portland', 'Remote'],
    }
    db_module.upsert_resume('test_resume', str(resume_path), criteria)

    jobs_raw = [
        dict(resume_type='test_resume', source='hybrid_scraper',
             title='Senior SRE', company='Acme Corp',
             location='Portland, OR', salary='$150k',
             url='https://example.com/jobs/1',
             description='Build and operate cloud infrastructure with Kubernetes.',
             scraped_at='2026-01-01T09:00:00', search_query='SRE Portland OR'),
        dict(resume_type='test_resume', source='hybrid_scraper',
             title='DevOps Engineer', company='Beta Inc',
             location='Remote', salary='$130k',
             url='https://example.com/jobs/2',
             description='CI/CD pipelines and Kubernetes.',
             scraped_at='2026-01-01T09:05:00', search_query='SRE Portland OR'),
        dict(resume_type='test_resume', source='hybrid_scraper',
             title='Junior SRE', company='Gamma LLC',
             location='Dallas, TX', salary=None,
             url='https://example.com/jobs/3',
             description='Entry-level SRE position.',
             scraped_at='2026-01-01T09:10:00', search_query='DevOps Remote'),
        dict(resume_type='other_resume', source='hybrid_scraper',
             title='Platform Engineer', company='Delta Co',
             location='Remote', salary='$160k',
             url='https://example.com/jobs/4',
             description='Platform engineering role.',
             scraped_at='2026-01-01T09:15:00', search_query='Platform Remote'),
    ]

    ai_base = dict(
        keyword_matches=['Kubernetes', 'Terraform'],
        missing_keywords=[],
        experience_level='APPROPRIATE',
        experience_reasoning='Good fit.',
        ats_pass_likelihood='HIGH',
        ats_reasoning='Keywords match.',
        role_fit='EXCELLENT',
        role_fit_reasoning='Strong alignment.',
        competitive_strengths=['K8s expertise'],
        competitive_gaps=[],
        should_apply='DEFINITELY',
        application_strategy='Apply now.',
        interview_red_flags=[],
        interview_green_flags=[],
        interview_warning='NONE',
        interview_reasoning='',
        confidence=0.90,
        overall_reasoning='Strong match.',
    )

    analyses = [
        dict(decision='STRONG_MATCH', fit_score=0.92),
        dict(decision='APPLY',        fit_score=0.75),
        dict(decision='SKIP',         fit_score=0.30),
        dict(decision='STRONG_MATCH', fit_score=0.91),
    ]

    job_ids = []
    for job in jobs_raw:
        job_ids.append(db_module.upsert_job(**job))

    for job_id, analysis in zip(job_ids, analyses):
        db_module.upsert_analysis(
            job_id=job_id,
            decision=analysis['decision'],
            fit_score=analysis['fit_score'],
            quick_checks={'title_match': True},
            ai_analysis={**ai_base, **analysis},
        )

    return job_ids


@pytest.fixture(scope='module')
def _app(tmp_path_factory):
    """
    Module-scoped: reload ui.app once per test file.
    All tests in a file share this Flask app instance.

    ui.app is a singleton module object — multiple test files share it.
    We snapshot all mutated module-level state before setup and restore
    it on teardown so each test file leaves the module as it found it.
    """
    tmp = tmp_path_factory.mktemp('integration')
    db_path = tmp / 'test.db'

    import ui.app as app_module

    original_db_path = db_module.DB_PATH
    original_project_root = app_module.PROJECT_ROOT
    original_env_path = app_module.ENV_PATH

    db_module.DB_PATH = db_path

    with patch('core.database.init_db'), \
         patch('core.database.import_from_json', return_value=0), \
         patch('core.database.migrate_resumes_from_fs', return_value=0):
        importlib.reload(app_module)

    db_module.init_db()

    app_module.PROJECT_ROOT = tmp
    app_module.ENV_PATH = tmp / '.env'
    app_module.app.config['TESTING'] = True

    yield app_module, tmp

    db_module.DB_PATH = original_db_path
    app_module.PROJECT_ROOT = original_project_root
    app_module.ENV_PATH = original_env_path


@pytest.fixture
def client(_app):
    """
    Function-scoped: clear and re-seed DB before each test.
    Yields a Flask test client with c.job_ids set to the seeded IDs.
    """
    app_module, tmp = _app
    _clear_db()
    job_ids = _seed_db(tmp)

    with app_module.app.test_client() as c:
        c.job_ids = job_ids
        yield c


@pytest.fixture
def mock_ai():
    """Patch analyze_job_fit so /api/analyze-single doesn't hit the API."""
    result = {
        'decision': 'STRONG_MATCH',
        'fit_score': 0.92,
        'quick_analysis': {
            'title_match': True, 'senior_level_match': True,
            'location_compatible': True, 'obvious_dealbreakers': [],
        },
        'ai_analysis': {
            'keyword_matches': ['Kubernetes', 'Terraform'],
            'missing_keywords': [],
            'experience_level': 'APPROPRIATE',
            'experience_reasoning': 'Good fit.',
            'ats_pass_likelihood': 'HIGH',
            'ats_reasoning': 'Keywords match.',
            'role_fit': 'EXCELLENT',
            'role_fit_reasoning': 'Strong alignment.',
            'competitive_strengths': ['K8s expertise'],
            'competitive_gaps': [],
            'should_apply': 'DEFINITELY',
            'application_strategy': 'Apply now.',
            'interview_red_flags': [],
            'interview_green_flags': [],
            'interview_warning': 'NONE',
            'interview_reasoning': '',
            'confidence': 0.92,
            'overall_reasoning': 'Strong match.',
        },
    }
    with patch('core.agent.analyze_job_fit', return_value=result) as m:
        yield m
