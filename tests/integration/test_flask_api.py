"""
Integration tests for ui/app.py Flask routes.

All tests use the `client` fixture from conftest.py which provides:
  - Isolated temp SQLite DB (not the real data/applicationagent.db)
  - 4 seeded jobs: 3 for 'test_resume', 1 for 'other_resume'
  - 1 seeded resume: 'test_resume'
  - Flask test client in TESTING mode

No Anthropic API calls, no subprocess spawns, no browser.
"""

import base64
import json
from io import BytesIO
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock
import pytest

pytestmark = pytest.mark.integration


# ── GET / ─────────────────────────────────────────────────────────────────────

class TestIndex:

    def test_returns_200(self, client):
        rv = client.get('/')
        assert rv.status_code == 200

    def test_returns_html(self, client):
        rv = client.get('/')
        assert b'ApplicationAgent' in rv.data


# ── GET /api/results ──────────────────────────────────────────────────────────

class TestApiResults:

    def test_returns_all_results(self, client):
        rv = client.get('/api/results')
        data = rv.get_json()
        assert rv.status_code == 200
        assert data['count'] == 4

    def test_filters_by_resume_type(self, client):
        rv = client.get('/api/results?resume_type=test_resume')
        data = rv.get_json()
        assert data['count'] == 3
        assert all(r['job_metadata']['company'] != 'Delta Co' for r in data['results'])

    def test_result_shape(self, client):
        rv = client.get('/api/results?resume_type=test_resume')
        r = rv.get_json()['results'][0]
        assert 'id' in r
        assert 'decision' in r
        assert 'fit_score' in r
        assert 'job_metadata' in r
        assert 'ai_analysis' in r

    def test_sorted_by_score_descending(self, client):
        rv = client.get('/api/results?resume_type=test_resume')
        scores = [r['fit_score'] for r in rv.get_json()['results']]
        assert scores == sorted(scores, reverse=True)

    def test_empty_resume_type_returns_all(self, client):
        rv = client.get('/api/results?resume_type=')
        assert rv.get_json()['count'] == 4


# ── GET /api/resumes ──────────────────────────────────────────────────────────

class TestApiResumes:

    def test_returns_seeded_resume(self, client):
        rv = client.get('/api/resumes')
        data = rv.get_json()
        assert rv.status_code == 200
        names = [r['name'] for r in data['resumes']]
        assert 'test_resume' in names

    def test_resume_has_stats(self, client):
        rv = client.get('/api/resumes')
        resume = next(r for r in rv.get_json()['resumes'] if r['name'] == 'test_resume')
        assert 'stats' in resume
        assert resume['stats']['total_jobs'] == 3

    def test_resume_detail_by_id(self, client):
        resumes = client.get('/api/resumes').get_json()['resumes']
        resume_id = resumes[0]['id']
        rv = client.get(f'/api/resumes/{resume_id}')
        assert rv.status_code == 200
        assert rv.get_json()['name'] == 'test_resume'

    def test_resume_detail_missing_returns_404(self, client):
        rv = client.get('/api/resumes/99999')
        assert rv.status_code == 404


# ── PUT /api/resumes/<id> ─────────────────────────────────────────────────────

class TestUpdateResume:

    def _get_resume_id(self, client):
        return client.get('/api/resumes').get_json()['resumes'][0]['id']

    def test_update_criteria_returns_ok(self, client, tmp_path):
        resume_id = self._get_resume_id(client)
        new_criteria = {
            'search_queries': [{'keywords': 'SRE', 'location': 'Remote', 'max_results': 10}],
            'exclude_keywords': ['Clearance'],
            'location_preferences': ['Remote'],
        }
        rv = client.put(f'/api/resumes/{resume_id}',
                        json={'search_criteria': new_criteria})
        assert rv.status_code == 200
        assert rv.get_json()['status'] == 'ok'

    def test_update_missing_resume_returns_404(self, client):
        rv = client.put('/api/resumes/99999', json={'search_criteria': {}})
        assert rv.status_code == 404

    def test_update_missing_body_returns_400(self, client):
        resume_id = self._get_resume_id(client)
        rv = client.put(f'/api/resumes/{resume_id}', json={})
        assert rv.status_code == 400


# ── DELETE /api/resumes/<id> ──────────────────────────────────────────────────

class TestDeleteResume:

    def test_delete_requires_confirm(self, client):
        resumes = client.get('/api/resumes').get_json()['resumes']
        resume_id = resumes[0]['id']
        rv = client.delete(f'/api/resumes/{resume_id}')
        assert rv.status_code == 400

    def test_delete_with_confirm(self, client):
        resumes = client.get('/api/resumes').get_json()['resumes']
        resume_id = resumes[0]['id']
        rv = client.delete(f'/api/resumes/{resume_id}?confirm=true')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['deleted'] is True
        # Jobs for that resume should also be gone
        assert data['jobs_deleted'] == 3


# ── POST /api/applied / DELETE /api/applied ───────────────────────────────────

class TestApplied:

    def test_mark_applied(self, client):
        job_id = client.job_ids[0]
        rv = client.post(f'/api/applied/{job_id}')
        assert rv.status_code == 200
        results = client.get('/api/results?resume_type=test_resume').get_json()['results']
        match = next(r for r in results if r['id'] == job_id)
        assert match['applied'] is True

    def test_unmark_applied(self, client):
        job_id = client.job_ids[0]
        client.post(f'/api/applied/{job_id}')
        rv = client.delete(f'/api/applied/{job_id}')
        assert rv.status_code == 200
        results = client.get('/api/results?resume_type=test_resume').get_json()['results']
        match = next(r for r in results if r['id'] == job_id)
        assert match['applied'] is False


# ── POST /api/consider/<id> ───────────────────────────────────────────────────

class TestConsider:

    def test_sets_consider_decision(self, client):
        job_id = client.job_ids[2]  # SKIP job
        rv = client.post(f'/api/consider/{job_id}',
                         json={'fit_score': 0.30})
        assert rv.status_code == 200
        assert rv.get_json()['decision'] == 'CONSIDER'
        results = client.get('/api/results?resume_type=test_resume').get_json()['results']
        match = next(r for r in results if r['id'] == job_id)
        assert match['decision'] == 'CONSIDER'


# ── POST /api/delete-job ──────────────────────────────────────────────────────

class TestDeleteJob:

    def test_delete_removes_job(self, client):
        job_id = client.job_ids[2]
        rv = client.post('/api/delete-job',
                         json={'id': job_id, 'title': 'Junior SRE', 'company': 'Gamma LLC'})
        assert rv.status_code == 200
        results = client.get('/api/results?resume_type=test_resume').get_json()['results']
        assert not any(r['id'] == job_id for r in results)

    def test_delete_missing_id_returns_400(self, client):
        rv = client.post('/api/delete-job', json={})
        assert rv.status_code == 400

    def test_delete_nonexistent_job_is_ok(self, client):
        rv = client.post('/api/delete-job',
                         json={'id': 99999, 'title': 'Ghost', 'company': 'Nowhere'})
        assert rv.status_code == 200


# ── GET /api/scrapers ─────────────────────────────────────────────────────────

class TestScrapers:

    def test_returns_scraper_list(self, client):
        rv = client.get('/api/scrapers')
        assert rv.status_code == 200
        data = rv.get_json()
        assert 'scrapers' in data
        assert isinstance(data['scrapers'], list)

    def test_includes_hybrid_scraper(self, client):
        data = client.get('/api/scrapers').get_json()
        names = [s['name'] for s in data['scrapers']]
        assert 'hybrid_scraper' in names


# ── GET /api/data-files ───────────────────────────────────────────────────────

class TestDataFiles:

    def test_returns_empty_when_no_files(self, client):
        rv = client.get('/api/data-files?resume_type=test_resume')
        assert rv.status_code == 200
        assert rv.get_json()['files'] == []

    def test_lists_json_files_in_scraped_dir(self, client, _app):
        _, app_tmp = _app
        scraped_dir = app_tmp / 'data' / 'scraped'
        scraped_dir.mkdir(parents=True, exist_ok=True)
        (scraped_dir / 'hybrid_scraper_test_resume_2026-01-01.json').write_text('{}')
        rv = client.get('/api/data-files?resume_type=test_resume')
        assert 'hybrid_scraper_test_resume_2026-01-01.json' in rv.get_json()['files']


# ── GET /api/settings/status ──────────────────────────────────────────────────

class TestSettingsStatus:

    def test_returns_status(self, client):
        rv = client.get('/api/settings/status')
        assert rv.status_code == 200
        data = rv.get_json()
        assert 'api_key_configured' in data
        assert 'requires_reentry' in data

    def test_no_key_in_db_means_not_configured(self, client):
        # Fresh DB has no key hash — both flags false
        import os
        os.environ.pop('ANTHROPIC_API_KEY', None)
        rv = client.get('/api/settings/status')
        data = rv.get_json()
        assert data['api_key_configured'] is False
        assert data['requires_reentry'] is False

    def test_key_in_db_but_not_memory_means_requires_reentry(self, client):
        import os
        from core.keystore import set_key
        set_key('sk-ant-test-key-reentry')
        os.environ.pop('ANTHROPIC_API_KEY', None)
        rv = client.get('/api/settings/status')
        data = rv.get_json()
        assert data['api_key_configured'] is False
        assert data['requires_reentry'] is True

    def test_key_in_memory_means_configured(self, client):
        import os
        from core.keystore import set_key
        set_key('sk-ant-test-key-inmemory')
        rv = client.get('/api/settings/status')
        data = rv.get_json()
        assert data['api_key_configured'] is True
        assert data['requires_reentry'] is False


# ── POST /api/settings/apikey ─────────────────────────────────────────────────

class TestSettingsApiKey:

    def test_missing_key_returns_400(self, client):
        rv = client.post('/api/settings/apikey', json={})
        assert rv.status_code == 400

    def test_invalid_key_format_returns_400(self, client):
        rv = client.post('/api/settings/apikey', json={'api_key': 'not-a-key'})
        assert rv.status_code == 400

    def test_valid_key_returns_ok(self, client):
        rv = client.post('/api/settings/apikey',
                         json={'api_key': 'sk-ant-test-key-1234567890'})
        assert rv.status_code == 200
        assert rv.get_json()['status'] == 'ok'

    def test_valid_key_sets_environ(self, client):
        import os
        rv = client.post('/api/settings/apikey',
                         json={'api_key': 'sk-ant-test-key-environ'})
        assert rv.status_code == 200
        assert os.environ.get('ANTHROPIC_API_KEY') == 'sk-ant-test-key-environ'

    def test_valid_key_stored_as_hash_in_db(self, client):
        from core.keystore import is_key_configured, verify_key
        rv = client.post('/api/settings/apikey',
                         json={'api_key': 'sk-ant-test-key-hashcheck'})
        assert rv.status_code == 200
        assert is_key_configured()
        assert verify_key('sk-ant-test-key-hashcheck')

    def test_plaintext_key_not_written_to_env_file(self, client, _app):
        _, app_tmp = _app
        client.post('/api/settings/apikey',
                    json={'api_key': 'sk-ant-test-key-noplaintext'})
        env_path = app_tmp / '.env'
        if env_path.exists():
            assert 'sk-ant-test-key-noplaintext' not in env_path.read_text()


# ── POST /api/analyze-single ──────────────────────────────────────────────────

class TestAnalyzeSingle:

    def test_analyze_single_returns_decision(self, client, mock_ai, tmp_path):
        rv = client.post('/api/analyze-single', json={
            'resume_type': 'test_resume',
            'job_name': 'Senior SRE',
            'company': 'TestCo',
            'job_description': 'Build Kubernetes infrastructure at scale.',
        })
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['decision'] == 'STRONG_MATCH'
        assert data['fit_score'] == 0.92

    def test_analyze_single_saves_to_db(self, client, mock_ai):
        client.post('/api/analyze-single', json={
            'resume_type': 'test_resume',
            'job_name': 'Integration Test Job',
            'company': 'TestCo',
            'job_description': 'Some job description.',
        })
        results = client.get('/api/results?resume_type=test_resume').get_json()
        titles = [r['job_metadata']['title'] for r in results['results']]
        assert 'Integration Test Job' in titles

    def test_analyze_single_missing_resume_returns_400(self, client, mock_ai):
        rv = client.post('/api/analyze-single', json={
            'resume_type': 'nonexistent_resume',
            'job_name': 'Job',
            'company': 'Co',
            'job_description': 'Description.',
        })
        assert rv.status_code == 400

    def test_analyze_single_missing_fields_returns_400(self, client):
        rv = client.post('/api/analyze-single', json={})
        assert rv.status_code == 400


# ── GET /api/run (SSE) ────────────────────────────────────────────────────────

class TestApiRun:

    def _mock_proc(self, lines):
        proc = MagicMock()
        proc.stdout = iter(line + '\n' for line in lines)
        proc.wait.return_value = 0
        return proc

    def test_run_streams_done_sentinel(self, client):
        with patch('subprocess.Popen', return_value=self._mock_proc(['Step 1', 'Step 2'])):
            rv = client.get('/api/run?resume_type=test_resume&mode=full'
                            '&reset_cache=false&scraper=hybrid_scraper')
        assert rv.status_code == 200
        assert b'__done__' in rv.data

    def test_run_streams_output_lines(self, client):
        with patch('subprocess.Popen', return_value=self._mock_proc(['STEP 1: SCRAPING'])):
            rv = client.get('/api/run?resume_type=test_resume&mode=full'
                            '&reset_cache=false&scraper=hybrid_scraper')
        assert b'STEP 1: SCRAPING' in rv.data

    def test_run_missing_resume_type_returns_400(self, client):
        rv = client.get('/api/run')
        assert rv.status_code == 400

    def test_run_nonexistent_resume_returns_400(self, client):
        rv = client.get('/api/run?resume_type=no_such_resume&mode=full'
                        '&reset_cache=false&scraper=hybrid_scraper')
        assert rv.status_code == 400


# ── POST /api/upload-resume ───────────────────────────────────────────────────

def _b64(content: bytes) -> str:
    return base64.b64encode(content).decode()


class TestUploadResume:

    def _form(self, name='new_resume', content=b'Experienced engineer.', filename='resume.txt',
              queries=None, keywords=None):
        queries = queries if queries is not None else [{'keywords': 'SRE', 'location': 'Remote', 'max_results': 10}]
        keywords = keywords or []
        return {
            'name': name,
            'filename': filename,
            'file_data': _b64(content),
            'search_queries': queries,
            'keywords': keywords,
        }

    def test_upload_txt_creates_resume(self, client):
        rv = client.post('/api/upload-resume',
                         json=self._form())
        assert rv.status_code == 200
        assert rv.get_json()['name'] == 'new_resume'
        resumes = client.get('/api/resumes').get_json()['resumes']
        assert any(r['name'] == 'new_resume' for r in resumes)

    def test_upload_missing_name_returns_400(self, client):
        rv = client.post('/api/upload-resume',
                         json=self._form(name=''))
        assert rv.status_code == 400

    def test_upload_invalid_name_returns_400(self, client):
        rv = client.post('/api/upload-resume',
                         json=self._form(name='bad name!'))
        assert rv.status_code == 400

    def test_upload_missing_file_returns_400(self, client):
        rv = client.post('/api/upload-resume',
                         json={
                             'name': 'new_resume',
                             'filename': 'resume.txt',
                             'file_data': '',
                             'search_queries': [{'keywords': 'SRE', 'location': 'Remote', 'max_results': 10}],
                             'keywords': [],
                         })
        assert rv.status_code == 400

    def test_upload_no_queries_returns_400(self, client):
        rv = client.post('/api/upload-resume',
                         json=self._form(queries=[]))
        assert rv.status_code == 400

    def test_upload_pdf_uses_fitz(self, client):
        """PDF upload path: fitz extracts text, .txt file is written."""
        fake_page = MagicMock()
        fake_page.get_text.return_value = 'Extracted resume text from PDF.'
        fake_doc = MagicMock()
        fake_doc.__iter__ = lambda self: iter([fake_page])
        with patch('fitz.open', return_value=fake_doc):
            rv = client.post('/api/upload-resume',
                             json=self._form(content=b'%PDF-fake', filename='resume.pdf'))
        assert rv.status_code == 200

    def test_upload_too_large_returns_413(self, client):
        oversized = b'x' * (10 * 1024 * 1024 + 1)
        rv = client.post('/api/upload-resume',
                         json=self._form(content=oversized))
        assert rv.status_code == 413


# ── POST /api/resumes/<id>/upload ─────────────────────────────────────────────

class TestUploadResumeVersion:

    def _resume_id(self, client):
        return client.get('/api/resumes').get_json()['resumes'][0]['id']

    def test_upload_txt_version(self, client):
        resume_id = self._resume_id(client)
        rv = client.post(f'/api/resumes/{resume_id}/upload',
                         json={'filename': 'resume.txt', 'file_data': _b64(b'Updated resume content.')})
        assert rv.status_code == 200
        assert rv.get_json()['status'] == 'ok'

    def test_upload_missing_file_returns_400(self, client):
        resume_id = self._resume_id(client)
        rv = client.post(f'/api/resumes/{resume_id}/upload',
                         json={'filename': 'resume.txt', 'file_data': ''})
        assert rv.status_code == 400

    def test_upload_wrong_type_returns_400(self, client):
        resume_id = self._resume_id(client)
        rv = client.post(f'/api/resumes/{resume_id}/upload',
                         json={'filename': 'resume.docx', 'file_data': _b64(b'data')})
        assert rv.status_code == 400

    def test_upload_nonexistent_resume_returns_404(self, client):
        rv = client.post('/api/resumes/99999/upload',
                         json={'filename': 'resume.txt', 'file_data': _b64(b'text')})
        assert rv.status_code == 404

    def test_upload_pdf_version_uses_fitz(self, client):
        resume_id = self._resume_id(client)
        fake_page = MagicMock()
        fake_page.get_text.return_value = 'Updated PDF resume text.'
        fake_doc = MagicMock()
        fake_doc.__iter__ = lambda self: iter([fake_page])
        with patch('fitz.open', return_value=fake_doc):
            rv = client.post(f'/api/resumes/{resume_id}/upload',
                             json={'filename': 'resume.pdf', 'file_data': _b64(b'%PDF-fake')})
        assert rv.status_code == 200

    def test_upload_too_large_returns_413(self, client):
        resume_id = self._resume_id(client)
        oversized = b'x' * (10 * 1024 * 1024 + 1)
        rv = client.post(f'/api/resumes/{resume_id}/upload',
                         json={'filename': 'resume.txt', 'file_data': _b64(oversized)})
        assert rv.status_code == 413


# ── POST /api/extract-job-screenshot ─────────────────────────────────────────

def _mock_vision_response(company='Acme Corp', title='Senior SRE',
                           salary='$150,000 - $180,000', url='https://example.com/job',
                           confidence=0.92):
    """Build a mock Anthropic response for the vision extraction endpoint."""
    payload = json.dumps({
        'company': company, 'title': title,
        'salary': salary, 'url': url,
        'confidence': confidence,
    })
    content = MagicMock()
    content.text = payload
    response = MagicMock()
    response.content = [content]
    return response


def _screenshot_post(client, content=b'fake-image-bytes', mimetype='image/png'):
    return client.post(
        '/api/extract-job-screenshot',
        data={'image': (BytesIO(content), 'screenshot.png', mimetype)},
        content_type='multipart/form-data',
    )


class TestExtractJobScreenshot:

    def test_success_returns_all_fields(self, client):
        mock_resp = _mock_vision_response()
        with patch('anthropic.Anthropic') as MockClient:
            MockClient.return_value.messages.create.return_value = mock_resp
            rv = _screenshot_post(client)
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['company'] == 'Acme Corp'
        assert data['title'] == 'Senior SRE'
        assert data['salary'] == '$150,000 - $180,000'
        assert data['url'] == 'https://example.com/job'
        assert data['confidence'] == 0.92

    def test_partial_extraction_null_fields_present(self, client):
        """Null fields must be present in response so JS can skip them cleanly."""
        mock_resp = _mock_vision_response(salary=None, url=None, confidence=0.80)
        with patch('anthropic.Anthropic') as MockClient:
            MockClient.return_value.messages.create.return_value = mock_resp
            rv = _screenshot_post(client)
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['company'] == 'Acme Corp'
        assert data['title'] == 'Senior SRE'
        assert data['salary'] is None
        assert data['url'] is None

    def test_low_confidence_still_returns_200(self, client):
        """Low confidence is surfaced via the confidence field, not an error code."""
        mock_resp = _mock_vision_response(confidence=0.40)
        with patch('anthropic.Anthropic') as MockClient:
            MockClient.return_value.messages.create.return_value = mock_resp
            rv = _screenshot_post(client)
        assert rv.status_code == 200
        assert rv.get_json()['confidence'] == 0.40

    def test_vision_api_failure_returns_500_json(self, client):
        with patch('anthropic.Anthropic') as MockClient:
            MockClient.return_value.messages.create.side_effect = Exception('API down')
            rv = _screenshot_post(client)
        assert rv.status_code == 500
        assert 'error' in rv.get_json()

    def test_no_image_returns_400(self, client):
        rv = client.post('/api/extract-job-screenshot',
                         data={}, content_type='multipart/form-data')
        assert rv.status_code == 400

    def test_unsupported_mimetype_returns_400(self, client):
        rv = client.post(
            '/api/extract-job-screenshot',
            data={'image': (BytesIO(b'data'), 'doc.pdf', 'application/pdf')},
            content_type='multipart/form-data',
        )
        assert rv.status_code == 400

    def test_oversized_image_returns_413(self, client):
        big = b'x' * (10 * 1024 * 1024 + 1)
        rv = _screenshot_post(client, content=big)
        assert rv.status_code == 413


# ── GET /output/pdf/<filename> ────────────────────────────────────────────────

class TestServePdf:

    def test_serves_existing_pdf(self, client, _app):
        _, app_tmp = _app
        pdf_dir = app_tmp / 'output' / 'pdf'
        pdf_dir.mkdir(parents=True, exist_ok=True)
        (pdf_dir / 'test_job.pdf').write_bytes(b'%PDF-1.4 fake content')
        rv = client.get('/output/pdf/test_job.pdf')
        assert rv.status_code == 200
        assert rv.content_type == 'application/pdf'

    def test_missing_pdf_returns_404(self, client):
        rv = client.get('/output/pdf/nonexistent.pdf')
        assert rv.status_code == 404

    def test_non_pdf_extension_returns_404(self, client, _app):
        _, app_tmp = _app
        pdf_dir = app_tmp / 'output' / 'pdf'
        pdf_dir.mkdir(parents=True, exist_ok=True)
        (pdf_dir / 'resume.txt').write_text('not a pdf')
        rv = client.get('/output/pdf/resume.txt')
        assert rv.status_code == 404


# ── GET /docs/ and /docs/<filename> ──────────────────────────────────────────

class TestServeDocs:

    def test_docs_index_lists_md_files(self, client, _app):
        _, app_tmp = _app
        docs_dir = app_tmp / 'docs'
        docs_dir.mkdir(exist_ok=True)
        # Do NOT create getting-started.md — /docs/ defaults to that filename.
        # If it doesn't exist, the route falls through to the index listing.
        (docs_dir / 'install.md').write_text('# Install\nSetup instructions.')
        rv = client.get('/docs/')
        assert rv.status_code == 200
        assert b'install.md' in rv.data

    def test_docs_renders_markdown_file(self, client, _app):
        _, app_tmp = _app
        docs_dir = app_tmp / 'docs'
        docs_dir.mkdir(exist_ok=True)
        (docs_dir / 'getting-started.md').write_text('# Getting Started\nHello world.')
        rv = client.get('/docs/getting-started.md')
        assert rv.status_code == 200
        assert b'Getting Started' in rv.data

    def test_docs_missing_file_shows_index(self, client, _app):
        _, app_tmp = _app
        docs_dir = app_tmp / 'docs'
        docs_dir.mkdir(exist_ok=True)
        rv = client.get('/docs/no-such-file.md')
        assert rv.status_code == 200
        assert b'Documentation' in rv.data

    def test_docs_non_md_extension_shows_index(self, client, _app):
        _, app_tmp = _app
        docs_dir = app_tmp / 'docs'
        docs_dir.mkdir(exist_ok=True)
        (docs_dir / 'notes.txt').write_text('plain text')
        rv = client.get('/docs/notes.txt')
        assert rv.status_code == 200
        assert b'Documentation' in rv.data


# ── POST /api/forward/<job_id> ────────────────────────────────────────────────

class TestForwardToPipeorgan:

    def test_forward_unknown_job_returns_404(self, client):
        rv = client.post('/api/forward/99999')
        assert rv.status_code == 404
        assert rv.get_json()['error'] == 'job not found'

    def test_forward_success_returns_forwarded(self, client):
        job_id = client.job_ids[0]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'id': 'po-123', 'status': 'queued'}
        mock_resp.raise_for_status.return_value = None
        with patch('requests.post', return_value=mock_resp):
            rv = client.post(f'/api/forward/{job_id}')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['status'] == 'forwarded'
        assert data['pipeorgan'] == {'id': 'po-123', 'status': 'queued'}

    def test_forward_pipeorgan_down_returns_502(self, client):
        job_id = client.job_ids[0]
        with patch('requests.post', side_effect=Exception('connection refused')):
            rv = client.post(f'/api/forward/{job_id}')
        assert rv.status_code == 502
        assert 'connection refused' in rv.get_json()['error']
