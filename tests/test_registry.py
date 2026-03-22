"""
Tests for scrapers/registry.py and scrapers/base.py

No browser launched, no network calls. Tests plugin discovery and
the BaseScraper save_results helper.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch


# ── registry ──────────────────────────────────────────────────────────────────

class TestGetScrapers:

    def test_returns_list(self):
        from scrapers.registry import get_scrapers
        result = get_scrapers()
        assert isinstance(result, list)

    def test_includes_hybrid_scraper(self):
        from scrapers.registry import get_scrapers
        names = [s['name'] for s in get_scrapers()]
        assert 'hybrid_scraper' in names

    def test_each_entry_has_name_and_display_name(self):
        from scrapers.registry import get_scrapers
        for s in get_scrapers():
            assert 'name' in s
            assert 'display_name' in s
            assert isinstance(s['name'], str)
            assert isinstance(s['display_name'], str)

    def test_sorted_by_display_name(self):
        from scrapers.registry import get_scrapers
        result = get_scrapers()
        display_names = [s['display_name'] for s in result]
        assert display_names == sorted(display_names)


class TestGetScraper:

    def test_returns_hybrid_scraper_class(self):
        from scrapers.registry import get_scraper
        cls = get_scraper('hybrid_scraper')
        assert cls.__name__ == 'HybridScraper'

    def test_unknown_name_raises_value_error(self):
        from scrapers.registry import get_scraper
        with pytest.raises(ValueError, match='hybrid_scraper'):
            get_scraper('no_such_scraper')

    def test_returned_class_has_correct_name_attr(self):
        from scrapers.registry import get_scraper
        cls = get_scraper('hybrid_scraper')
        assert cls.name == 'hybrid_scraper'

    def test_returned_class_has_display_name_attr(self):
        from scrapers.registry import get_scraper
        cls = get_scraper('hybrid_scraper')
        assert cls.display_name


# ── BaseScraper.save_results ──────────────────────────────────────────────────

class TestBaseScrapeResults:
    """Test save_results via a minimal stub (HybridScraper overrides the signature)."""

    @pytest.fixture
    def scraper(self, tmp_path):
        from scrapers.base import BaseScraper

        class _StubScraper(BaseScraper):
            name = 'stub_scraper'
            display_name = 'Stub Scraper'
            def scrape(self, output_dir): pass  # noqa: E704

        criteria = {
            'search_queries': [],
            'exclude_keywords': [],
        }
        criteria_path = tmp_path / 'criteria.json'
        criteria_path.write_text(json.dumps(criteria))
        return _StubScraper(
            search_criteria_path=str(criteria_path),
            resume_type='test_resume',
        )

    def test_save_results_writes_to_scraped_subdir(self, scraper, tmp_path):
        jobs = [{'title': 'SRE', 'company': 'Acme', 'location': 'Remote',
                 'salary': None, 'url': 'https://ex.com/1',
                 'description': 'Build infra.', 'scraped_at': '2026-01-01T00:00:00',
                 'search_query': 'SRE Remote'}]
        output_file = scraper.save_results(jobs, str(tmp_path))
        assert Path(output_file).exists()
        assert 'scraped' in str(Path(output_file).parent)

    def test_save_results_filename_contains_scraper_name(self, scraper, tmp_path):
        output_file = scraper.save_results([], str(tmp_path))
        assert scraper.name in Path(output_file).name

    def test_save_results_filename_contains_resume_type(self, scraper, tmp_path):
        output_file = scraper.save_results([], str(tmp_path))
        assert 'test_resume' in Path(output_file).name

    def test_save_results_source_field_is_scraper_name(self, scraper, tmp_path):
        output_file = scraper.save_results([], str(tmp_path))
        data = json.loads(Path(output_file).read_text())
        assert data['source'] == scraper.name

    def test_save_results_jobs_written_correctly(self, scraper, tmp_path):
        jobs = [{'title': 'SRE', 'company': 'Acme'}]
        output_file = scraper.save_results(jobs, str(tmp_path))
        data = json.loads(Path(output_file).read_text())
        assert data['total_jobs'] == 1
        assert data['jobs'][0]['title'] == 'SRE'
