"""
Tests for scripts/batch_analyzer.py

Covers: load_scraped_jobs, generate_pdf_report, analyze_batch, print_summary.
All AI and DB calls are mocked — no real API calls or production DB access.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.batch_analyzer import (
    load_scraped_jobs,
    generate_pdf_report,
    analyze_batch,
    print_summary,
)

FIXTURES_DIR = Path(__file__).parent / 'fixtures'


# ── load_scraped_jobs ──────────────────────────────────────────────────────────

class TestLoadScrapedJobs:

    def test_loads_valid_json(self, tmp_path):
        data = {'jobs': [{'title': 'SRE', 'company': 'Acme'}], 'scraped_at': '2026-01-01'}
        f = tmp_path / 'jobs.json'
        f.write_text(json.dumps(data))
        result = load_scraped_jobs(str(f))
        assert result['jobs'][0]['title'] == 'SRE'
        assert result['scraped_at'] == '2026-01-01'

    def test_loads_fixture_file(self):
        result = load_scraped_jobs(str(FIXTURES_DIR / 'sample_jobs.json'))
        assert len(result['jobs']) == 3
        assert result['resume_type'] == 'test_resume'

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_scraped_jobs(str(tmp_path / 'nonexistent.json'))


# ── generate_pdf_report ────────────────────────────────────────────────────────

class TestGeneratePdfReport:

    def _result(self, decision='STRONG_MATCH', score=0.92, **ai_overrides):
        ai = {
            'keyword_matches': ['Kubernetes', 'Terraform'],
            'missing_keywords': ['Go'],
            'experience_level': 'APPROPRIATE',
            'experience_reasoning': 'Good fit.',
            'ats_pass_likelihood': 'HIGH',
            'ats_reasoning': 'Keywords match.',
            'role_fit': 'EXCELLENT',
            'role_fit_reasoning': 'Strong alignment.',
            'competitive_strengths': ['K8s expertise'],
            'competitive_gaps': ['No Go experience'],
            'should_apply': 'DEFINITELY',
            'application_strategy': 'Emphasize K8s projects.',
            'interview_red_flags': [],
            'interview_green_flags': ['Systems design focus'],
            'interview_warning': 'NONE',
            'interview_reasoning': 'No concerns.',
            'confidence': 0.92,
            'overall_reasoning': 'Strong match across all dimensions.',
        }
        ai.update(ai_overrides)
        return {
            'decision': decision,
            'fit_score': score,
            'ai_analysis': ai,
            'job_metadata': {
                'title': 'Senior SRE',
                'company': 'TechCorp',
                'location': 'Portland, OR',
                'salary': '$150k',
                'url': 'https://example.com/jobs/sre-001',
            },
        }

    def test_creates_pdf_file(self, tmp_path):
        result = self._result()
        pdf_path = generate_pdf_report(result, output_dir=str(tmp_path))
        assert Path(pdf_path).exists()
        assert pdf_path.endswith('.pdf')

    def test_filename_uses_company_and_title(self, tmp_path):
        result = self._result()
        pdf_path = generate_pdf_report(result, output_dir=str(tmp_path))
        assert 'TechCorp' in pdf_path
        assert 'Senior_SRE' in pdf_path or 'Senior SRE'.replace(' ', '_') in pdf_path

    def test_creates_output_dir_if_missing(self, tmp_path):
        nested = tmp_path / 'deep' / 'nested' / 'pdfs'
        result = self._result()
        pdf_path = generate_pdf_report(result, output_dir=str(nested))
        assert nested.exists()
        assert Path(pdf_path).exists()

    def test_skip_decision_generates_pdf(self, tmp_path):
        result = self._result(decision='SKIP', score=0.30)
        pdf_path = generate_pdf_report(result, output_dir=str(tmp_path))
        assert Path(pdf_path).exists()

    def test_apply_decision_generates_pdf(self, tmp_path):
        result = self._result(decision='APPLY', score=0.75)
        pdf_path = generate_pdf_report(result, output_dir=str(tmp_path))
        assert Path(pdf_path).exists()

    def test_interview_warning_included(self, tmp_path):
        result = self._result(interview_warning='SEVERE',
                              interview_red_flags=['6-round loop', 'Unpaid take-home'],
                              interview_reasoning='Excessive rounds.')
        pdf_path = generate_pdf_report(result, output_dir=str(tmp_path))
        assert Path(pdf_path).exists()

    def test_special_chars_in_company_name(self, tmp_path):
        result = self._result()
        result['job_metadata']['company'] = 'A & B (Corp) LLC!'
        pdf_path = generate_pdf_report(result, output_dir=str(tmp_path))
        assert Path(pdf_path).exists()

    def test_no_salary_does_not_crash(self, tmp_path):
        result = self._result()
        result['job_metadata']['salary'] = None
        pdf_path = generate_pdf_report(result, output_dir=str(tmp_path))
        assert Path(pdf_path).exists()

    def test_overwrite_existing_pdf(self, tmp_path):
        result = self._result()
        path1 = generate_pdf_report(result, output_dir=str(tmp_path))
        path2 = generate_pdf_report(result, output_dir=str(tmp_path))
        assert path1 == path2  # same path, overwritten


# ── print_summary ──────────────────────────────────────────────────────────────

class TestPrintSummary:

    def _result(self, decision, score, title='SRE', company='Corp', location='Remote', url='https://ex.com/1'):
        return {
            'decision': decision,
            'fit_score': score,
            'job_metadata': {
                'title': title,
                'company': company,
                'location': location,
                'url': url,
            },
        }

    def test_prints_without_error(self, capsys):
        results = [
            self._result('STRONG_MATCH', 0.95, url='https://ex.com/1'),
            self._result('APPLY', 0.75, url='https://ex.com/2'),
            self._result('MAYBE', 0.55, url='https://ex.com/3'),
            self._result('SKIP', 0.30, url='https://ex.com/4'),
        ]
        print_summary(results)
        out = capsys.readouterr().out
        assert 'STRONG_MATCH' in out
        assert 'APPLY' in out
        assert 'SKIP' in out

    def test_empty_results(self, capsys):
        print_summary([])
        out = capsys.readouterr().out
        assert 'RANKED RESULTS' in out

    def test_counts_correct(self, capsys):
        results = [
            self._result('STRONG_MATCH', 0.95, url='https://ex.com/1'),
            self._result('STRONG_MATCH', 0.91, url='https://ex.com/2'),
            self._result('SKIP', 0.2, url='https://ex.com/3'),
        ]
        print_summary(results)
        out = capsys.readouterr().out
        assert 'Apply to: 2 STRONG_MATCH + 0 APPLY = 2 jobs' in out


# ── analyze_batch ──────────────────────────────────────────────────────────────

class TestAnalyzeBatch:

    def _make_jobs_file(self, tmp_path, resume_type='test_resume'):
        data = {
            'resume_type': resume_type,
            'scraped_at': '2026-03-09T10:00:00',
            'jobs': [
                {
                    'id': 'job-001',
                    'title': 'Senior SRE',
                    'company': 'TechCorp',
                    'location': 'Portland, OR',
                    'salary': '$150k',
                    'url': 'https://example.com/job-001',
                    'description': 'Build K8s infra, 10+ years DevOps experience required.',
                    'scraped_at': '2026-03-09T10:00:00',
                    'search_query': 'Site Reliability Engineer Portland',
                },
            ],
        }
        f = tmp_path / 'jobs.json'
        f.write_text(json.dumps(data))
        return str(f)

    def _make_resume(self, tmp_path):
        resume = tmp_path / 'my_resume.txt'
        resume.write_text('DevOps/SRE engineer. Kubernetes, Terraform, AWS. 15 years experience.')
        return str(resume)

    def _mock_ai_result(self):
        return {
            'decision': 'STRONG_MATCH',
            'fit_score': 0.92,
            'quick_analysis': {
                'title_match': True,
                'senior_level_match': True,
                'location_compatible': True,
                'obvious_dealbreakers': [],
            },
            'ai_analysis': {
                'keyword_matches': ['Kubernetes', 'Terraform'],
                'missing_keywords': [],
                'experience_level': 'APPROPRIATE',
                'experience_reasoning': 'Good.',
                'ats_pass_likelihood': 'HIGH',
                'ats_reasoning': 'Good match.',
                'role_fit': 'EXCELLENT',
                'role_fit_reasoning': 'Perfect fit.',
                'competitive_strengths': ['K8s'],
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
            'timestamp': '2026-03-09T10:00:00',
            'resume_type': 'test_resume',
        }

    @patch('scripts.batch_analyzer.generate_pdf_report')
    @patch('scripts.batch_analyzer.upsert_analysis')
    @patch('scripts.batch_analyzer.upsert_job', return_value=1)
    @patch('scripts.batch_analyzer.analyze_job_fit')
    @patch('scripts.batch_analyzer.init_db')
    def test_analyze_batch_returns_job_count(
        self, mock_init, mock_analyze, mock_upsert_job, mock_upsert_analysis,
        mock_pdf, tmp_path
    ):
        mock_analyze.return_value = self._mock_ai_result()
        mock_pdf.return_value = str(tmp_path / 'report.pdf')

        jobs_file = self._make_jobs_file(tmp_path)
        resume_file = self._make_resume(tmp_path)

        count = analyze_batch(jobs_file, resume_file)
        assert count == 1

    @patch('scripts.batch_analyzer.generate_pdf_report')
    @patch('scripts.batch_analyzer.upsert_analysis')
    @patch('scripts.batch_analyzer.upsert_job', return_value=1)
    @patch('scripts.batch_analyzer.analyze_job_fit')
    @patch('scripts.batch_analyzer.init_db')
    def test_analyze_batch_calls_init_db(
        self, mock_init, mock_analyze, mock_upsert_job, mock_upsert_analysis,
        mock_pdf, tmp_path
    ):
        mock_analyze.return_value = self._mock_ai_result()
        mock_pdf.return_value = str(tmp_path / 'report.pdf')

        jobs_file = self._make_jobs_file(tmp_path)
        resume_file = self._make_resume(tmp_path)

        analyze_batch(jobs_file, resume_file)
        mock_init.assert_called_once()

    @patch('scripts.batch_analyzer.generate_pdf_report')
    @patch('scripts.batch_analyzer.upsert_analysis')
    @patch('scripts.batch_analyzer.upsert_job', return_value=2)
    @patch('scripts.batch_analyzer.analyze_job_fit')
    @patch('scripts.batch_analyzer.init_db')
    def test_analyze_batch_calls_upsert_job(
        self, mock_init, mock_analyze, mock_upsert_job, mock_upsert_analysis,
        mock_pdf, tmp_path
    ):
        mock_analyze.return_value = self._mock_ai_result()
        mock_pdf.return_value = str(tmp_path / 'report.pdf')

        jobs_file = self._make_jobs_file(tmp_path)
        resume_file = self._make_resume(tmp_path)

        analyze_batch(jobs_file, resume_file)
        mock_upsert_job.assert_called_once()
        call_kwargs = mock_upsert_job.call_args
        assert call_kwargs.kwargs['title'] == 'Senior SRE'
        assert call_kwargs.kwargs['company'] == 'TechCorp'

    @patch('scripts.batch_analyzer.generate_pdf_report')
    @patch('scripts.batch_analyzer.upsert_analysis')
    @patch('scripts.batch_analyzer.upsert_job', return_value=2)
    @patch('scripts.batch_analyzer.analyze_job_fit')
    @patch('scripts.batch_analyzer.init_db')
    def test_analyze_batch_upsert_analysis_called(
        self, mock_init, mock_analyze, mock_upsert_job, mock_upsert_analysis,
        mock_pdf, tmp_path
    ):
        mock_analyze.return_value = self._mock_ai_result()
        mock_pdf.return_value = str(tmp_path / 'report.pdf')

        jobs_file = self._make_jobs_file(tmp_path)
        resume_file = self._make_resume(tmp_path)

        analyze_batch(jobs_file, resume_file)
        mock_upsert_analysis.assert_called_once_with(
            job_id=2,
            decision='STRONG_MATCH',
            fit_score=0.92,
            quick_checks=mock_analyze.return_value['quick_analysis'],
            ai_analysis=mock_analyze.return_value['ai_analysis'],
        )

    @patch('scripts.batch_analyzer.generate_pdf_report')
    @patch('scripts.batch_analyzer.upsert_analysis')
    @patch('scripts.batch_analyzer.upsert_job', return_value=1)
    @patch('scripts.batch_analyzer.analyze_job_fit')
    @patch('scripts.batch_analyzer.init_db')
    def test_analyze_batch_generates_pdf_for_all_decisions(
        self, mock_init, mock_analyze, mock_upsert_job, mock_upsert_analysis,
        mock_pdf, tmp_path
    ):
        ai_result = self._mock_ai_result()
        ai_result['decision'] = 'SKIP'
        ai_result['fit_score'] = 0.30
        mock_analyze.return_value = ai_result
        mock_pdf.return_value = str(tmp_path / 'report.pdf')

        jobs_file = self._make_jobs_file(tmp_path)
        resume_file = self._make_resume(tmp_path)

        analyze_batch(jobs_file, resume_file)
        mock_pdf.assert_called_once()

    @patch('scripts.batch_analyzer.generate_pdf_report')
    @patch('scripts.batch_analyzer.upsert_analysis')
    @patch('scripts.batch_analyzer.upsert_job', return_value=None)
    @patch('scripts.batch_analyzer.analyze_job_fit')
    @patch('scripts.batch_analyzer.init_db')
    def test_analyze_batch_skips_upsert_analysis_when_no_job_id(
        self, mock_init, mock_analyze, mock_upsert_job, mock_upsert_analysis,
        mock_pdf, tmp_path
    ):
        mock_analyze.return_value = self._mock_ai_result()
        mock_pdf.return_value = str(tmp_path / 'report.pdf')

        jobs_file = self._make_jobs_file(tmp_path)
        resume_file = self._make_resume(tmp_path)

        analyze_batch(jobs_file, resume_file)
        mock_upsert_analysis.assert_not_called()

    @patch('scripts.batch_analyzer.generate_pdf_report', side_effect=Exception('PDF error'))
    @patch('scripts.batch_analyzer.upsert_analysis')
    @patch('scripts.batch_analyzer.upsert_job', return_value=1)
    @patch('scripts.batch_analyzer.analyze_job_fit')
    @patch('scripts.batch_analyzer.init_db')
    def test_pdf_error_does_not_abort_batch(
        self, mock_init, mock_analyze, mock_upsert_job, mock_upsert_analysis,
        mock_pdf, tmp_path, capsys
    ):
        mock_analyze.return_value = self._mock_ai_result()

        jobs_file = self._make_jobs_file(tmp_path)
        resume_file = self._make_resume(tmp_path)

        # Should complete without raising
        count = analyze_batch(jobs_file, resume_file)
        assert count == 1
        out = capsys.readouterr().out
        assert 'Error' in out

    @patch('scripts.batch_analyzer.generate_pdf_report')
    @patch('scripts.batch_analyzer.upsert_analysis')
    @patch('scripts.batch_analyzer.upsert_job', return_value=1)
    @patch('scripts.batch_analyzer.analyze_job_fit')
    @patch('scripts.batch_analyzer.init_db')
    def test_source_from_json_field(
        self, mock_init, mock_analyze, mock_upsert_job, mock_upsert_analysis,
        mock_pdf, tmp_path
    ):
        """source in JSON takes precedence over filename."""
        mock_analyze.return_value = self._mock_ai_result()
        mock_pdf.return_value = str(tmp_path / 'report.pdf')

        data = json.loads(Path(self._make_jobs_file(tmp_path)).read_text())
        data['source'] = 'my_custom_scraper'
        f = tmp_path / 'hybrid_scraper_test_resume_2026-01-01.json'
        f.write_text(json.dumps(data))

        analyze_batch(str(f), self._make_resume(tmp_path))

        call_kwargs = mock_upsert_job.call_args.kwargs
        assert call_kwargs['source'] == 'my_custom_scraper'

    @patch('scripts.batch_analyzer.generate_pdf_report')
    @patch('scripts.batch_analyzer.upsert_analysis')
    @patch('scripts.batch_analyzer.upsert_job', return_value=1)
    @patch('scripts.batch_analyzer.analyze_job_fit')
    @patch('scripts.batch_analyzer.init_db')
    def test_source_falls_back_to_filename_prefix(
        self, mock_init, mock_analyze, mock_upsert_job, mock_upsert_analysis,
        mock_pdf, tmp_path
    ):
        """When JSON has no source, derive from filename stem prefix."""
        mock_analyze.return_value = self._mock_ai_result()
        mock_pdf.return_value = str(tmp_path / 'report.pdf')

        data = json.loads(Path(self._make_jobs_file(tmp_path)).read_text())
        # No 'source' key
        data.pop('source', None)
        f = tmp_path / 'my_plugin_test_resume_2026-01-01.json'
        f.write_text(json.dumps(data))

        analyze_batch(str(f), self._make_resume(tmp_path))

        call_kwargs = mock_upsert_job.call_args.kwargs
        assert call_kwargs['source'] == 'my_plugin'
