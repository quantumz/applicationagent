"""
Pipeline integration tests — seam A to seam B.

Tests the full data flow without a browser or live API:
  sample_jobs.json  →  analyze_batch (mocked AI)  →  DB  →  /api/results

This is the critical path that unit tests cannot cover: verifying that data
written by batch_analyzer is correctly read back by the Flask API layer.
"""

import json
from pathlib import Path
from unittest.mock import patch
import pytest

import core.database as db_module

FIXTURES_DIR = Path(__file__).parent.parent / 'fixtures'


def _ai_result(decision='STRONG_MATCH', score=0.92):
    return {
        'decision': decision,
        'fit_score': score,
        'quick_analysis': {
            'title_match': True, 'senior_level_match': True,
            'location_compatible': True, 'obvious_dealbreakers': [],
        },
        'ai_analysis': {
            'keyword_matches': ['Kubernetes'], 'missing_keywords': [],
            'experience_level': 'APPROPRIATE', 'experience_reasoning': 'Good.',
            'ats_pass_likelihood': 'HIGH', 'ats_reasoning': 'Good match.',
            'role_fit': 'EXCELLENT', 'role_fit_reasoning': 'Perfect fit.',
            'competitive_strengths': ['K8s'], 'competitive_gaps': [],
            'should_apply': 'DEFINITELY', 'application_strategy': 'Apply.',
            'interview_red_flags': [], 'interview_green_flags': [],
            'interview_warning': 'NONE', 'interview_reasoning': '',
            'confidence': score, 'overall_reasoning': 'Strong.',
        },
        'timestamp': '2026-01-01T00:00:00',
        'resume_type': 'test_resume',
    }


# ── Full pipeline: scraper JSON → analyze_batch → DB → /api/results ──────────

class TestScraperToApi:

    @pytest.fixture(autouse=True)
    def reset(self, _app):
        """Clear DB before each test in this class."""
        import sqlite3
        with sqlite3.connect(str(db_module.DB_PATH)) as conn:
            conn.execute('DELETE FROM analysis')
            conn.execute('DELETE FROM applied_jobs')
            conn.execute('DELETE FROM jobs')
            conn.execute('DELETE FROM resumes')
            conn.commit()

    def test_analyze_batch_jobs_appear_in_api(self, _app, tmp_path):
        app_module, _ = _app
        resume_path = tmp_path / 'test_resume.txt'
        resume_path.write_text('Experienced SRE. Kubernetes, Terraform, AWS.')

        with patch('scripts.batch_analyzer.analyze_job_fit', return_value=_ai_result()), \
             patch('scripts.batch_analyzer.generate_pdf_report', return_value='fake.pdf'):
            from scripts.batch_analyzer import analyze_batch
            count = analyze_batch(
                str(FIXTURES_DIR / 'sample_jobs.json'),
                str(resume_path),
            )

        assert count == 3
        with app_module.app.test_client() as c:
            rv = c.get('/api/results?resume_type=test_resume')
            data = rv.get_json()
        assert data['count'] == 3

    def test_decisions_stored_correctly(self, _app, tmp_path):
        app_module, _ = _app
        resume_path = tmp_path / 'test_resume.txt'
        resume_path.write_text('Experienced SRE.')

        decisions = ['STRONG_MATCH', 'APPLY', 'SKIP']
        call_count = 0

        def rotating_ai(*args, **kwargs):
            nonlocal call_count
            result = _ai_result(
                decision=decisions[call_count % len(decisions)],
                score=[0.92, 0.75, 0.30][call_count % 3],
            )
            call_count += 1
            return result

        with patch('scripts.batch_analyzer.analyze_job_fit', side_effect=rotating_ai), \
             patch('scripts.batch_analyzer.generate_pdf_report', return_value='fake.pdf'):
            from scripts.batch_analyzer import analyze_batch
            analyze_batch(
                str(FIXTURES_DIR / 'sample_jobs.json'),
                str(resume_path),
            )

        with app_module.app.test_client() as c:
            results = c.get('/api/results?resume_type=test_resume').get_json()['results']

        returned_decisions = {r['decision'] for r in results}
        assert 'STRONG_MATCH' in returned_decisions
        assert 'APPLY' in returned_decisions
        assert 'SKIP' in returned_decisions

    def test_source_field_stored_from_json(self, _app, tmp_path):
        """Source written by batch_analyzer is readable via API result metadata."""
        app_module, _ = _app
        resume_path = tmp_path / 'test_resume.txt'
        resume_path.write_text('Experienced SRE.')

        with patch('scripts.batch_analyzer.analyze_job_fit', return_value=_ai_result()), \
             patch('scripts.batch_analyzer.generate_pdf_report', return_value='fake.pdf'):
            from scripts.batch_analyzer import analyze_batch
            analyze_batch(
                str(FIXTURES_DIR / 'sample_jobs.json'),
                str(resume_path),
            )

        # Verify via DB directly — source is not surfaced in /api/results JSON
        jobs = db_module.get_all_jobs_for_resume('test_resume')
        assert all(j['source'] == 'hybrid_scraper' for j in jobs)

    def test_consider_override_survives_reanalysis(self, _app, tmp_path):
        """
        A job manually marked CONSIDER must not be overwritten when
        analyze_batch re-runs on the same jobs.
        """
        app_module, _ = _app
        resume_path = tmp_path / 'test_resume.txt'
        resume_path.write_text('Experienced SRE.')

        # First run: insert jobs
        with patch('scripts.batch_analyzer.analyze_job_fit', return_value=_ai_result('SKIP', 0.30)), \
             patch('scripts.batch_analyzer.generate_pdf_report', return_value='fake.pdf'):
            from scripts.batch_analyzer import analyze_batch
            analyze_batch(str(FIXTURES_DIR / 'sample_jobs.json'), str(resume_path))

        # Mark first job as CONSIDER
        jobs = db_module.get_all_jobs_for_resume('test_resume')
        consider_id = jobs[0]['id']
        db_module.set_consider(consider_id, 0.30)

        # Second run: re-analyze same jobs
        with patch('scripts.batch_analyzer.analyze_job_fit', return_value=_ai_result('SKIP', 0.30)), \
             patch('scripts.batch_analyzer.generate_pdf_report', return_value='fake.pdf'):
            analyze_batch(str(FIXTURES_DIR / 'sample_jobs.json'), str(resume_path))

        # CONSIDER must still be CONSIDER
        with app_module.app.test_client() as c:
            results = c.get('/api/results?resume_type=test_resume').get_json()['results']
        match = next(r for r in results if r['id'] == consider_id)
        assert match['decision'] == 'CONSIDER'
