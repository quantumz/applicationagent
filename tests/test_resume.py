"""
Tests for core/resume.py — load_resume() and load_location_preferences().
"""

import json
import pytest
from pathlib import Path

from core.resume import load_resume, load_location_preferences


def _make_resume(tmp_path, resume_type, text='Sample resume text.'):
    """Create a minimal resume directory with a .txt file."""
    resume_dir = tmp_path / 'resumes' / resume_type
    resume_dir.mkdir(parents=True)
    (resume_dir / f'{resume_type}.txt').write_text(text)
    return resume_dir


def _write_criteria(resume_dir, resume_type, criteria):
    (resume_dir / f'{resume_type}_search_criteria.json').write_text(json.dumps(criteria))


# ── load_resume ───────────────────────────────────────────────────────────────

class TestLoadResume:

    def test_returns_resume_text(self, tmp_path):
        _make_resume(tmp_path, 'sre', text='Experienced SRE. Kubernetes. AWS.')
        text = load_resume('sre', tmp_path)
        assert text == 'Experienced SRE. Kubernetes. AWS.'

    def test_raises_when_txt_missing(self, tmp_path):
        (tmp_path / 'resumes' / 'sre').mkdir(parents=True)
        with pytest.raises(FileNotFoundError, match='Resume not found'):
            load_resume('sre', tmp_path)

    def test_raises_when_resume_dir_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError, match='Resume not found'):
            load_resume('nonexistent', tmp_path)

    def test_error_message_contains_path(self, tmp_path):
        with pytest.raises(FileNotFoundError) as exc_info:
            load_resume('missing_type', tmp_path)
        assert 'missing_type' in str(exc_info.value)

    def test_preserves_whitespace_and_newlines(self, tmp_path):
        content = 'Line one\n  indented\nLine three\n'
        _make_resume(tmp_path, 'sre', text=content)
        assert load_resume('sre', tmp_path) == content


# ── load_location_preferences ─────────────────────────────────────────────────

class TestLoadLocationPreferences:

    def test_returns_none_when_no_criteria_file(self, tmp_path):
        _make_resume(tmp_path, 'sre')
        assert load_location_preferences('sre', tmp_path) is None

    def test_returns_none_when_resume_dir_missing(self, tmp_path):
        assert load_location_preferences('nonexistent', tmp_path) is None

    def test_returns_none_when_key_absent_from_criteria(self, tmp_path):
        resume_dir = _make_resume(tmp_path, 'sre')
        _write_criteria(resume_dir, 'sre', {'search_queries': ['SRE']})
        assert load_location_preferences('sre', tmp_path) is None

    def test_returns_preferences_list(self, tmp_path):
        resume_dir = _make_resume(tmp_path, 'sre')
        _write_criteria(resume_dir, 'sre', {'location_preferences': ['Portland', 'Remote']})
        result = load_location_preferences('sre', tmp_path)
        assert result == ['Portland', 'Remote']

    def test_returns_empty_list_when_configured_as_empty(self, tmp_path):
        resume_dir = _make_resume(tmp_path, 'sre')
        _write_criteria(resume_dir, 'sre', {'location_preferences': []})
        result = load_location_preferences('sre', tmp_path)
        assert result == []

    def test_single_preference(self, tmp_path):
        resume_dir = _make_resume(tmp_path, 'sre')
        _write_criteria(resume_dir, 'sre', {'location_preferences': ['Remote']})
        assert load_location_preferences('sre', tmp_path) == ['Remote']
