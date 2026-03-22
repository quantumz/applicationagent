"""
Tests for core/agent.py — quick checks, score calculation, and AI analysis.

perform_quick_checks() and calculate_fit_score() are pure functions — no mocks.
analyze_job_fit() patches the Anthropic client to avoid API calls.
"""

import json
from unittest.mock import MagicMock, patch
import pytest

from core.agent import perform_quick_checks, calculate_fit_score, analyze_job_fit


# ── perform_quick_checks ──────────────────────────────────────────────────────

class TestPerformQuickChecks:

    def test_devops_title_match(self, sample_resume, strong_match_job):
        result = perform_quick_checks(strong_match_job, sample_resume)
        assert result['title_match'] is True

    def test_no_title_match_wrong_domain(self, sample_resume):
        job = "Marketing Manager needed. Run email campaigns and manage social media."
        result = perform_quick_checks(job, sample_resume)
        assert result['title_match'] is False

    def test_senior_level_detected(self, strong_match_job, sample_resume):
        result = perform_quick_checks(strong_match_job, sample_resume)
        assert result['senior_level_match'] is True

    def test_senior_level_not_detected_for_junior(self, sample_resume):
        job = "Junior developer role. Entry level welcome. 0-2 years."
        result = perform_quick_checks(job, sample_resume)
        assert result['senior_level_match'] is False

    def test_location_compatible_with_preferences(self, strong_match_job, sample_resume):
        prefs = ['Portland', 'Remote']
        result = perform_quick_checks(strong_match_job, sample_resume, location_preferences=prefs)
        assert result['location_compatible'] is True

    def test_location_incompatible(self, sample_resume):
        job = "On-site role in Dallas, TX only. Must work from office full-time."
        result = perform_quick_checks(job, sample_resume, location_preferences=['Portland', 'Remote'])
        assert result['location_compatible'] is False

    def test_location_match_uses_preferences_not_hardcode(self, sample_resume):
        # Non-Portland prefs must work — guards against any hardcoded city in logic
        result = perform_quick_checks(
            'Senior SRE role in Austin, TX. Remote-friendly.',
            sample_resume,
            location_preferences=['Austin', 'Remote'],
        )
        assert result['location_compatible'] is True

    def test_location_none_means_all_compatible(self, sample_resume):
        job = "On-site role in Dallas, TX. No remote work."
        result = perform_quick_checks(job, sample_resume, location_preferences=None)
        assert result['location_compatible'] is True

    def test_clearance_dealbreaker(self, sample_resume):
        job = "Senior DevOps engineer. Security clearance required. Remote OK."
        result = perform_quick_checks(job, sample_resume)
        assert any('clearance' in db.lower() for db in result['obvious_dealbreakers'])

    def test_relocation_dealbreaker(self, sample_resume):
        job = "Platform engineer. Relocation required to Austin TX. On-site only."
        result = perform_quick_checks(job, sample_resume)
        assert any('relocation' in db.lower() for db in result['obvious_dealbreakers'])

    def test_no_dealbreakers_for_clean_job(self, strong_match_job, sample_resume):
        result = perform_quick_checks(strong_match_job, sample_resume)
        assert result['obvious_dealbreakers'] == []

    def test_multiple_dealbreakers_accumulate(self, sample_resume):
        job = "Junior SRE. Security clearance required. Relocation required. On-site only."
        result = perform_quick_checks(job, sample_resume)
        assert len(result['obvious_dealbreakers']) >= 2


# ── calculate_fit_score ───────────────────────────────────────────────────────

class TestCalculateFitScore:

    def _make_quick(self, title_match=True, senior=True, location=True, dealbreakers=None):
        return {
            'title_match': title_match,
            'senior_level_match': senior,
            'location_compatible': location,
            'obvious_dealbreakers': dealbreakers or [],
        }

    def _make_ai(self, should_apply='DEFINITELY', ats='HIGH', exp='APPROPRIATE', warning='NONE'):
        return {
            'should_apply': should_apply,
            'ats_pass_likelihood': ats,
            'experience_level': exp,
            'interview_warning': warning,
        }

    def test_strong_signals_produce_high_score(self):
        score = calculate_fit_score(self._make_quick(), self._make_ai())
        assert score >= 0.7

    def test_weak_signals_produce_low_score(self):
        quick = self._make_quick(title_match=False, senior=False, location=False)
        ai = self._make_ai(should_apply='NO', ats='LOW', exp='UNDER_QUALIFIED', warning='SEVERE')
        score = calculate_fit_score(quick, ai)
        assert score < 0.5

    def test_score_clamped_to_zero(self):
        quick = self._make_quick(title_match=False, senior=False, location=False,
                                  dealbreakers=['clearance', 'phd', 'relocation'])
        ai = self._make_ai(should_apply='NO', ats='LOW', exp='UNDER_QUALIFIED', warning='SEVERE')
        score = calculate_fit_score(quick, ai)
        assert score >= 0.0

    def test_score_clamped_to_one(self):
        quick = self._make_quick()
        ai = self._make_ai()
        score = calculate_fit_score(quick, ai)
        assert score <= 1.0

    def test_dealbreaker_reduces_score(self):
        # Use reduced signals so scores don't both clamp to 1.0
        base_quick = self._make_quick(title_match=False, senior=False)
        base_ai = self._make_ai(ats='MEDIUM')
        clean = calculate_fit_score(base_quick, base_ai)
        dirty = calculate_fit_score({**base_quick, 'obvious_dealbreakers': ['clearance']}, base_ai)
        assert dirty < clean

    def test_severe_interview_warning_reduces_score(self):
        no_warning = calculate_fit_score(self._make_quick(), self._make_ai(warning='NONE'))
        severe = calculate_fit_score(self._make_quick(), self._make_ai(warning='SEVERE'))
        assert severe < no_warning

    def test_probably_lower_than_definitely(self):
        # Use reduced signals to avoid clamping at 1.0
        weak_quick = self._make_quick(title_match=False, senior=False)
        definitely = calculate_fit_score(weak_quick, self._make_ai(should_apply='DEFINITELY', ats='MEDIUM'))
        probably = calculate_fit_score(weak_quick, self._make_ai(should_apply='PROBABLY', ats='MEDIUM'))
        assert definitely > probably

    def test_under_qualified_lower_than_appropriate(self):
        appropriate = calculate_fit_score(self._make_quick(), self._make_ai(exp='APPROPRIATE'))
        under = calculate_fit_score(self._make_quick(), self._make_ai(exp='UNDER_QUALIFIED'))
        assert appropriate > under


# ── analyze_job_fit (mocked API) ──────────────────────────────────────────────

class TestAnalyzeJobFit:

    def _mock_client(self, ai_response_dict):
        """Return a mock Anthropic client whose messages.create() returns JSON."""
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=json.dumps(ai_response_dict))]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_msg
        return mock_client

    def test_returns_strong_match(self, sample_resume, strong_match_job, mock_ai_response):
        with patch('core.agent.client', self._mock_client(mock_ai_response)):
            result = analyze_job_fit(strong_match_job, sample_resume, 'test_resume')
        assert result['decision'] == 'STRONG_MATCH'
        assert result['fit_score'] >= 0.7

    def test_result_shape(self, sample_resume, strong_match_job, mock_ai_response):
        with patch('core.agent.client', self._mock_client(mock_ai_response)):
            result = analyze_job_fit(strong_match_job, sample_resume, 'test_resume')
        assert 'decision' in result
        assert 'fit_score' in result
        assert 'quick_analysis' in result
        assert 'ai_analysis' in result
        assert 'resume_type' in result
        assert result['resume_type'] == 'test_resume'

    def test_skip_decision_for_bad_job(self, sample_resume, skip_job):
        bad_ai = {
            'keyword_matches': [],
            'missing_keywords': ['Kubernetes', 'Terraform', 'AWS'],
            'experience_level': 'OVER_QUALIFIED',
            'experience_reasoning': 'Way overqualified for junior QA.',
            'ats_pass_likelihood': 'LOW',
            'ats_reasoning': 'Keywords do not match.',
            'role_fit': 'POOR',
            'role_fit_reasoning': 'Wrong domain entirely.',
            'competitive_strengths': [],
            'competitive_gaps': ['QA experience', 'testing tools'],
            'should_apply': 'NO',
            'application_strategy': 'Skip this one.',
            'interview_red_flags': [],
            'interview_green_flags': [],
            'interview_warning': 'NONE',
            'interview_reasoning': '',
            'confidence': 0.95,
            'overall_reasoning': 'Not a match.',
        }
        with patch('core.agent.client', self._mock_client(bad_ai)):
            result = analyze_job_fit(skip_job, sample_resume, 'test_resume')
        assert result['decision'] in ('SKIP', 'MAYBE')
        assert result['fit_score'] < 0.6

    def test_api_failure_returns_error_analysis(self, sample_resume, strong_match_job):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API timeout")
        with patch('core.agent.client', mock_client):
            result = analyze_job_fit(strong_match_job, sample_resume, 'test_resume')
        assert result['ai_analysis']['should_apply'] == 'ERROR'
        assert 'decision' in result  # still returns a result dict

    def test_location_preferences_passed_to_quick_checks(self, sample_resume, mock_ai_response):
        job = "Senior SRE role. On-site in Dallas, TX only."
        with patch('core.agent.client', self._mock_client(mock_ai_response)):
            result = analyze_job_fit(job, sample_resume, 'test_resume',
                                     location_preferences=['Portland', 'Remote'])
        assert result['quick_analysis']['location_compatible'] is False

    def test_api_called_exactly_once(self, sample_resume, strong_match_job, mock_ai_response):
        mock_client = self._mock_client(mock_ai_response)
        with patch('core.agent.client', mock_client):
            analyze_job_fit(strong_match_job, sample_resume, 'test_resume')
        mock_client.messages.create.assert_called_once()
