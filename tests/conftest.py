"""
Shared pytest fixtures for ApplicationAgent tests.
"""

import json
import os
import sqlite3
from pathlib import Path
import pytest

FIXTURES_DIR = Path(__file__).parent / 'fixtures'


def pytest_addoption(parser):
    parser.addoption(
        '--live-api',
        action='store_true',
        default=False,
        help='Run live smoke test against real Anthropic API (costs ~$0.004)',
    )


def pytest_configure(config):
    config.addinivalue_line(
        'markers',
        'live: smoke test against real Anthropic API — requires --live-api flag and ANTHROPIC_API_KEY',
    )


@pytest.fixture
def sample_resume():
    return (FIXTURES_DIR / 'sample_resume.txt').read_text()


@pytest.fixture
def strong_match_job():
    return (
        "Senior Site Reliability Engineer — Remote, Portland preferred. "
        "10+ years experience with Kubernetes, Terraform, AWS, and Python. "
        "Build and operate our cloud-native platform. "
        "Expertise in Prometheus, Grafana, and incident response required. "
        "This is a senior-level role for an experienced DevOps/SRE engineer."
    )


@pytest.fixture
def skip_job():
    return (
        "Junior QA Engineer wanted. Entry-level position, 0-2 years experience. "
        "Will test web applications manually. Relocation to Dallas required. "
        "PhD in Computer Science preferred. Security clearance required."
    )


@pytest.fixture
def sample_jobs_data():
    with open(FIXTURES_DIR / 'sample_jobs.json') as f:
        return json.load(f)


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """
    Isolated SQLite DB for each test. Patches core.database.DB_PATH
    so all DB calls go to a temp file, not the real DB.
    """
    db_path = tmp_path / 'test.db'
    import core.database as db_module
    monkeypatch.setattr(db_module, 'DB_PATH', db_path)
    db_module.init_db()
    return db_path


@pytest.fixture
def mock_ai_response():
    """Canonical strong-match AI analysis response dict."""
    return {
        'keyword_matches': ['Kubernetes', 'Terraform', 'AWS', 'Python', 'Prometheus'],
        'missing_keywords': [],
        'experience_level': 'APPROPRIATE',
        'experience_reasoning': 'Candidate has 15+ years, role requires 10+.',
        'ats_pass_likelihood': 'HIGH',
        'ats_reasoning': 'Resume keywords match job description well.',
        'role_fit': 'EXCELLENT',
        'role_fit_reasoning': 'Background aligns perfectly with the role.',
        'competitive_strengths': ['Deep Kubernetes expertise', 'AWS migration experience'],
        'competitive_gaps': [],
        'should_apply': 'DEFINITELY',
        'application_strategy': 'Emphasize K8s and AWS migration projects.',
        'interview_red_flags': [],
        'interview_green_flags': ['Systems design focus'],
        'interview_warning': 'NONE',
        'interview_reasoning': 'No concerns.',
        'confidence': 0.92,
        'overall_reasoning': 'Strong match across all dimensions.',
    }
