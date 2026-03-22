"""
Tests for applicationagent.py — CLI argument parsing and reanalyze_jobs().

All external calls (AI API, scraper, tracker, PDF) are mocked.
No filesystem writes outside tmp_path.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

import applicationagent as app_module


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_resume(tmp_path, resume_type='test_resume', with_criteria=False):
    resume_dir = tmp_path / 'resumes' / resume_type
    resume_dir.mkdir(parents=True, exist_ok=True)
    (resume_dir / f'{resume_type}.txt').write_text('Experienced SRE with Kubernetes and AWS.')
    if with_criteria:
        criteria = {'location_preferences': ['Portland', 'Remote'], 'search_queries': []}
        (resume_dir / f'{resume_type}_search_criteria.json').write_text(json.dumps(criteria))
    return resume_dir


def fake_job(job_id=1, title='Senior SRE', company='Acme'):
    return {
        'id': job_id, 'title': title, 'company': company,
        'description': 'Build and operate our cloud platform.',
        'location': 'Remote', 'salary': '$150k', 'url': f'https://example.com/{job_id}',
        'scraped_at': '2026-01-01T00:00:00',
    }


def fake_result(decision='STRONG_MATCH', score=0.92):
    return {
        'decision': decision, 'fit_score': score,
        'quick_analysis': {'title_match': True, 'senior_level_match': True},
        'ai_analysis': {
            'role_fit': 'EXCELLENT', 'should_apply': 'DEFINITELY',
            'ats_pass_likelihood': 'HIGH', 'overall_reasoning': 'Great fit.',
        },
    }


# ── reanalyze_jobs ────────────────────────────────────────────────────────────

class TestReanalyzeJobs:

    def test_exits_when_resume_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_module, 'PROJECT_ROOT', tmp_path)
        with pytest.raises(SystemExit):
            app_module.reanalyze_jobs('no_such_resume')

    def test_analyzes_all_jobs_for_resume_type(self, tmp_path, monkeypatch, mock_ai_response):
        monkeypatch.setattr(app_module, 'PROJECT_ROOT', tmp_path)
        make_resume(tmp_path, 'test_resume')

        jobs = [fake_job(1), fake_job(2)]
        result = fake_result()

        with patch('core.database.get_all_jobs_for_resume', return_value=jobs), \
             patch('core.database.upsert_analysis') as mock_upsert, \
             patch('core.agent.analyze_job_fit', return_value=result), \
             patch('scripts.batch_analyzer.generate_pdf_report'):
            app_module.reanalyze_jobs('test_resume')

        assert mock_upsert.call_count == 2

    def test_uses_get_jobs_by_ids_when_ids_provided(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_module, 'PROJECT_ROOT', tmp_path)
        make_resume(tmp_path, 'test_resume')

        with patch('core.database.get_jobs_by_ids', return_value=[fake_job(5)]) as mock_by_ids, \
             patch('core.database.get_all_jobs_for_resume') as mock_all, \
             patch('core.database.upsert_analysis'), \
             patch('core.agent.analyze_job_fit', return_value=fake_result()), \
             patch('scripts.batch_analyzer.generate_pdf_report'):
            app_module.reanalyze_jobs('test_resume', job_ids=[5])

        mock_by_ids.assert_called_once_with([5])
        mock_all.assert_not_called()

    def test_no_jobs_returns_without_analysis(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_module, 'PROJECT_ROOT', tmp_path)
        make_resume(tmp_path, 'test_resume')

        with patch('core.database.get_all_jobs_for_resume', return_value=[]), \
             patch('core.database.upsert_analysis') as mock_upsert:
            app_module.reanalyze_jobs('test_resume')

        mock_upsert.assert_not_called()

    def test_continues_after_per_job_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_module, 'PROJECT_ROOT', tmp_path)
        make_resume(tmp_path, 'test_resume')

        jobs = [fake_job(1), fake_job(2)]

        with patch('core.database.get_all_jobs_for_resume', return_value=jobs), \
             patch('core.database.upsert_analysis') as mock_upsert, \
             patch('core.agent.analyze_job_fit', side_effect=Exception('API failure')):
            app_module.reanalyze_jobs('test_resume')  # must not raise

        mock_upsert.assert_not_called()

    def test_loads_location_preferences_from_criteria(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_module, 'PROJECT_ROOT', tmp_path)
        make_resume(tmp_path, 'test_resume', with_criteria=True)

        captured = {}

        def fake_analyze(job_description, resume_text, resume_type, location_preferences=None):
            captured['loc'] = location_preferences
            return fake_result()

        with patch('core.database.get_all_jobs_for_resume', return_value=[fake_job()]), \
             patch('core.database.upsert_analysis'), \
             patch('core.agent.analyze_job_fit', side_effect=fake_analyze), \
             patch('scripts.batch_analyzer.generate_pdf_report'):
            app_module.reanalyze_jobs('test_resume')

        assert captured['loc'] == ['Portland', 'Remote']

    def test_warns_on_missing_ids(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(app_module, 'PROJECT_ROOT', tmp_path)
        make_resume(tmp_path, 'test_resume')

        # Only job 1 found, job 99 missing
        with patch('core.database.get_jobs_by_ids', return_value=[fake_job(1)]), \
             patch('core.database.upsert_analysis'), \
             patch('core.agent.analyze_job_fit', return_value=fake_result()), \
             patch('scripts.batch_analyzer.generate_pdf_report'):
            app_module.reanalyze_jobs('test_resume', job_ids=[1, 99])

        out = capsys.readouterr().out
        assert 'WARNING' in out

    def test_generates_pdf_for_each_job(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_module, 'PROJECT_ROOT', tmp_path)
        make_resume(tmp_path, 'test_resume')

        jobs = [fake_job(1), fake_job(2)]

        with patch('core.database.get_all_jobs_for_resume', return_value=jobs), \
             patch('core.database.upsert_analysis'), \
             patch('core.agent.analyze_job_fit', return_value=fake_result()), \
             patch('scripts.batch_analyzer.generate_pdf_report') as mock_pdf:
            app_module.reanalyze_jobs('test_resume')

        assert mock_pdf.call_count == 2


# ── main() CLI ────────────────────────────────────────────────────────────────

class TestMainCLI:

    def _run(self, tmp_path, monkeypatch, args):
        monkeypatch.setattr(app_module, 'PROJECT_ROOT', tmp_path)
        with patch.object(sys, 'argv', ['applicationagent.py'] + args):
            app_module.main()

    def test_missing_resume_exits(self, tmp_path, monkeypatch):
        with pytest.raises(SystemExit):
            self._run(tmp_path, monkeypatch, ['no_such_resume'])

    def test_reanalyze_with_scrape_only_exits(self, tmp_path, monkeypatch):
        make_resume(tmp_path, 'test_resume')
        with pytest.raises(SystemExit):
            self._run(tmp_path, monkeypatch, ['test_resume', '--reanalyze', '--scrape-only'])

    def test_reanalyze_calls_reanalyze_jobs(self, tmp_path, monkeypatch):
        make_resume(tmp_path, 'test_resume')
        with patch.object(app_module, 'reanalyze_jobs') as mock_rj, \
             patch.object(sys, 'argv', ['applicationagent.py', 'test_resume', '--reanalyze']):
            monkeypatch.setattr(app_module, 'PROJECT_ROOT', tmp_path)
            app_module.main()
        mock_rj.assert_called_once_with('test_resume', None)

    def test_reanalyze_parses_job_ids(self, tmp_path, monkeypatch):
        make_resume(tmp_path, 'test_resume')
        with patch.object(app_module, 'reanalyze_jobs') as mock_rj, \
             patch.object(sys, 'argv', ['applicationagent.py', 'test_resume',
                                         '--reanalyze', '--job-ids', '5,12,18']):
            monkeypatch.setattr(app_module, 'PROJECT_ROOT', tmp_path)
            app_module.main()
        mock_rj.assert_called_once_with('test_resume', [5, 12, 18])

    def test_track_only_calls_tracker(self, tmp_path, monkeypatch):
        make_resume(tmp_path, 'test_resume')
        with patch('scripts.tracker.run_tracker') as mock_tracker, \
             patch.object(sys, 'argv', ['applicationagent.py', 'test_resume', '--track-only']):
            monkeypatch.setattr(app_module, 'PROJECT_ROOT', tmp_path)
            app_module.main()
        mock_tracker.assert_called_once()

    def test_analyze_only_skips_scraper(self, tmp_path, monkeypatch):
        make_resume(tmp_path, 'test_resume')
        data_file = tmp_path / 'data' / 'jobs.json'
        data_file.parent.mkdir()
        data_file.write_text('[]')

        with patch('scripts.batch_analyzer.analyze_batch') as mock_analyze, \
             patch('scripts.tracker.run_tracker'), \
             patch.object(sys, 'argv', ['applicationagent.py', 'test_resume',
                                         '--analyze-only', str(data_file)]):
            monkeypatch.setattr(app_module, 'PROJECT_ROOT', tmp_path)
            app_module.main()

        mock_analyze.assert_called_once()
        call_kwargs = mock_analyze.call_args
        assert str(data_file) in str(call_kwargs)

    def test_unknown_scraper_exits(self, tmp_path, monkeypatch):
        make_resume(tmp_path, 'test_resume', with_criteria=True)
        with patch('scrapers.registry.get_scraper', side_effect=ValueError('Unknown scraper: bogus')), \
             patch.object(sys, 'argv', ['applicationagent.py', 'test_resume', '--scraper', 'bogus']):
            monkeypatch.setattr(app_module, 'PROJECT_ROOT', tmp_path)
            with pytest.raises(SystemExit):
                app_module.main()

    def test_scraper_flag_delegates_to_registry(self, tmp_path, monkeypatch):
        make_resume(tmp_path, 'test_resume', with_criteria=True)
        mock_class = MagicMock()
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
        scraped_file = tmp_path / 'data' / 'scraped' / 'my_plugin_test_resume_2026-01-01.json'
        scraped_file.parent.mkdir(parents=True, exist_ok=True)
        scraped_file.write_text('[]')
        mock_instance.scrape.return_value = str(scraped_file)

        with patch('scrapers.registry.get_scraper', return_value=mock_class) as mock_get, \
             patch('scripts.batch_analyzer.analyze_batch'), \
             patch('scripts.tracker.run_tracker'), \
             patch.object(sys, 'argv', ['applicationagent.py', 'test_resume', '--scraper', 'my_plugin']):
            monkeypatch.setattr(app_module, 'PROJECT_ROOT', tmp_path)
            app_module.main()

        mock_get.assert_called_once_with('my_plugin')
