"""
Tests for ui/app.py routes — GET /api/jobs/<job_id>/detail.

Uses Flask test client, isolated in-memory DB, and tmp_path for resume files.
No live API calls.
"""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """
    Flask test client with:
    - isolated SQLite DB (via monkeypatch on DB_PATH)
    - PROJECT_ROOT pointed at tmp_path so resume file reads go there
    """
    import core.database as db_module
    db_path = tmp_path / 'test.db'
    monkeypatch.setattr(db_module, 'DB_PATH', db_path)
    db_module.init_db()

    # Patch PROJECT_ROOT in ui.app before importing the app
    import ui.app as app_module
    monkeypatch.setattr(app_module, 'PROJECT_ROOT', tmp_path)

    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as client:
        yield client, tmp_path, db_module


def _seed_job(db_module, tmp_path, resume_type='test_sre', write_resume=True):
    """Insert a job row and optionally write the resume .txt file."""
    job_id = db_module.upsert_job(
        resume_type=resume_type,
        source='hybrid_scraper',
        title='Senior SRE',
        company='Anthropic',
        location='Remote',
        salary='$200k',
        url='https://example.com/job/1',
        description='Build reliable systems at scale.',
        scraped_at='2026-04-12T10:00:00',
    )
    db_module.upsert_analysis(
        job_id=job_id,
        decision='STRONG_MATCH',
        fit_score=0.92,
        quick_checks={},
        ai_analysis={},
    )
    if write_resume:
        resume_dir = tmp_path / 'resumes' / resume_type
        resume_dir.mkdir(parents=True, exist_ok=True)
        (resume_dir / f'{resume_type}.txt').write_text('Gregory Weaver — Senior SRE resume text.')
    return job_id


class TestJobDetailRoute:

    def test_returns_correct_shape(self, app_client):
        client, tmp_path, db = app_client
        job_id = _seed_job(db, tmp_path)
        resp = client.get(f'/api/jobs/{job_id}/detail')
        assert resp.status_code == 200
        data = resp.get_json()
        for key in ('job_id', 'title', 'company', 'description', 'resume_type', 'resume_text'):
            assert key in data, f'missing key: {key}'

    def test_returns_correct_values(self, app_client):
        client, tmp_path, db = app_client
        job_id = _seed_job(db, tmp_path)
        data = client.get(f'/api/jobs/{job_id}/detail').get_json()
        assert data['job_id'] == job_id
        assert data['title'] == 'Senior SRE'
        assert data['company'] == 'Anthropic'
        assert data['description'] == 'Build reliable systems at scale.'
        assert data['resume_type'] == 'test_sre'

    def test_resume_text_matches_file(self, app_client):
        client, tmp_path, db = app_client
        job_id = _seed_job(db, tmp_path)
        data = client.get(f'/api/jobs/{job_id}/detail').get_json()
        assert data['resume_text'] == 'Gregory Weaver — Senior SRE resume text.'

    def test_404_unknown_job(self, app_client):
        client, tmp_path, db = app_client
        resp = client.get('/api/jobs/99999/detail')
        assert resp.status_code == 404

    def test_404_missing_resume_file(self, app_client):
        client, tmp_path, db = app_client
        # Seed job but do NOT write the resume file
        job_id = _seed_job(db, tmp_path, write_resume=False)
        resp = client.get(f'/api/jobs/{job_id}/detail')
        assert resp.status_code == 404
