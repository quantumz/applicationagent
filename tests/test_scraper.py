"""
Tests for scrapers/hybrid_scraper.py — pure logic only.

HybridScraper requires a config file; we use the real scraper_config.json
and a minimal in-memory search criteria dict written to a temp file.
No browser is launched. No network calls.
"""

import json
import pytest
from pathlib import Path

SCRAPERS_DIR = Path(__file__).parent.parent / 'scrapers'
CONFIG_PATH = SCRAPERS_DIR / 'scraper_config.json'


@pytest.fixture
def scraper(tmp_path):
    """Minimal HybridScraper with a temp search_criteria file."""
    criteria = {
        'search_queries': [
            {'keywords': 'devops engineer', 'location': 'Portland, OR', 'max_results': 5}
        ],
        'exclude_keywords': ['Security Clearance'],
        'location_preferences': ['Portland', 'Remote'],
    }
    criteria_path = tmp_path / 'test_criteria.json'
    criteria_path.write_text(json.dumps(criteria))

    from scrapers.hybrid_scraper import HybridScraper
    return HybridScraper(
        config_path=str(CONFIG_PATH),
        search_criteria_path=str(criteria_path),
        resume_type='test_resume',
    )


# ── should_exclude_job ────────────────────────────────────────────────────────

class TestShouldExcludeJob:

    def test_excludes_intern_in_title(self, scraper):
        scraper.exclude_keywords = ['intern']
        excluded, kw = scraper.should_exclude_job('Software Intern', 'Great company.')
        assert excluded is True
        assert kw == 'intern'

    def test_intern_in_description_not_excluded(self, scraper):
        scraper.exclude_keywords = ['intern']
        excluded, _ = scraper.should_exclude_job('Senior DevOps Engineer', 'We have an intern program.')
        assert excluded is False

    def test_excludes_junior_in_title(self, scraper):
        scraper.exclude_keywords = ['junior']
        excluded, _ = scraper.should_exclude_job('Junior DevOps Engineer', 'Some description.')
        assert excluded is True

    def test_excludes_custom_keyword_in_description(self, scraper):
        scraper.exclude_keywords = ['blockchain']
        excluded, kw = scraper.should_exclude_job('Senior Engineer', 'We build blockchain solutions.')
        assert excluded is True
        assert kw == 'blockchain'

    def test_no_match_returns_false(self, scraper):
        scraper.exclude_keywords = ['blockchain', 'junior']
        excluded, kw = scraper.should_exclude_job('Senior SRE', 'AWS Kubernetes Terraform.')
        assert excluded is False
        assert kw is None

    def test_empty_exclude_list_never_excludes(self, scraper):
        scraper.exclude_keywords = []
        excluded, _ = scraper.should_exclude_job('Junior Intern Engineer', 'security clearance required')
        assert excluded is False

    def test_case_insensitive_match(self, scraper):
        scraper.exclude_keywords = ['Security Clearance']
        excluded, _ = scraper.should_exclude_job(
            'Senior SRE', 'This role requires SECURITY CLEARANCE.')
        assert excluded is True

    def test_word_boundary_prevents_partial_match(self, scraper):
        # 'intern' should not match 'internal'
        scraper.exclude_keywords = ['intern']
        excluded, _ = scraper.should_exclude_job(
            'Senior Engineer - Internal Tools', 'Work on internal platform.')
        assert excluded is False


# ── build_search_url ──────────────────────────────────────────────────────────

class TestBuildSearchUrl:

    def test_basic_url_structure(self, scraper):
        url = scraper.build_search_url('devops engineer', 'Portland, OR')
        assert url.startswith('https://www.ziprecruiter.com/jobs-search')
        assert 'devops+engineer' in url
        assert 'Portland' in url

    def test_spaces_replaced_with_plus_in_keywords(self, scraper):
        url = scraper.build_search_url('site reliability engineer', 'Remote')
        assert 'site+reliability+engineer' in url

    def test_comma_encoded_in_location(self, scraper):
        url = scraper.build_search_url('devops', 'Portland, OR')
        assert '%2C' in url

    def test_location_spaces_replaced(self, scraper):
        url = scraper.build_search_url('devops', 'New York, NY')
        assert 'New+York' in url

    def test_single_word_keywords(self, scraper):
        url = scraper.build_search_url('kubernetes', 'Remote')
        assert 'kubernetes' in url
        assert 'Remote' in url


# ── _parse_posted_date ────────────────────────────────────────────────────────

class TestParsePostedDate:
    """Pure relative-date parser. We patch the datetime symbol in the scraper
    module so 'today' is deterministic across all assertions."""

    @pytest.fixture(autouse=True)
    def _freeze_now(self, monkeypatch):
        from datetime import datetime as _dt
        import scrapers.hybrid_scraper as mod

        frozen = _dt(2026, 5, 18, 12, 0, 0)

        class _FrozenDateTime(_dt):
            @classmethod
            def now(cls, tz=None):
                return frozen

        monkeypatch.setattr(mod, 'datetime', _FrozenDateTime)

    def test_none_input(self):
        from scrapers.hybrid_scraper import _parse_posted_date
        assert _parse_posted_date(None) is None

    def test_empty_string(self):
        from scrapers.hybrid_scraper import _parse_posted_date
        assert _parse_posted_date('') is None

    def test_no_posted_phrase(self):
        from scrapers.hybrid_scraper import _parse_posted_date
        assert _parse_posted_date('Renton, WA $72/hr Contractor') is None

    def test_days_ago(self):
        from scrapers.hybrid_scraper import _parse_posted_date
        assert _parse_posted_date('Posted 23 days ago') == '2026-04-25'

    def test_single_day_ago(self):
        from scrapers.hybrid_scraper import _parse_posted_date
        assert _parse_posted_date('Posted 1 day ago') == '2026-05-17'

    def test_today(self):
        from scrapers.hybrid_scraper import _parse_posted_date
        assert _parse_posted_date('Posted today') == '2026-05-18'

    def test_just_now(self):
        from scrapers.hybrid_scraper import _parse_posted_date
        assert _parse_posted_date('Posted just now') == '2026-05-18'

    def test_hours_ago_treated_as_today(self):
        from scrapers.hybrid_scraper import _parse_posted_date
        assert _parse_posted_date('Posted 5 hours ago') == '2026-05-18'

    def test_single_hour_ago(self):
        from scrapers.hybrid_scraper import _parse_posted_date
        assert _parse_posted_date('Posted 1 hour ago') == '2026-05-18'

    def test_case_insensitive(self):
        from scrapers.hybrid_scraper import _parse_posted_date
        assert _parse_posted_date('POSTED 3 DAYS AGO') == '2026-05-15'

    def test_embedded_in_blob(self):
        """The real-world case from the handoff."""
        from scrapers.hybrid_scraper import _parse_posted_date
        blob = 'Renton, WA Quick Apply $72/hr Contractor Life, PTO Posted 23 days ago'
        assert _parse_posted_date(blob) == '2026-04-25'

    def test_weeks_pattern_deferred_returns_none(self):
        """Documents the deferred case — flag if ZipRecruiter starts emitting this."""
        from scrapers.hybrid_scraper import _parse_posted_date
        assert _parse_posted_date('Posted 2 weeks ago') is None
