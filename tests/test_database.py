"""
Tests for core/database.py — CRUD operations on isolated temp DB.

Uses the `test_db` fixture from conftest.py which patches DB_PATH
so every test gets a clean in-process SQLite file.
"""

import pytest
import core.database as db


# ── upsert_job ────────────────────────────────────────────────────────────────

class TestUpsertJob:

    def _job(self, **overrides):
        defaults = dict(
            resume_type='test_resume',
            source='hybrid_scraper',
            title='Senior SRE',
            company='TechCorp',
            location='Portland, OR',
            salary='$150k',
            url='https://ziprecruiter.com/jobs/abc123',
            description='Great job.',
            scraped_at='2026-03-09T10:00:00',
        )
        return {**defaults, **overrides}

    def test_insert_returns_id(self, test_db):
        job_id = db.upsert_job(**self._job())
        assert isinstance(job_id, int)
        assert job_id > 0

    def test_duplicate_url_returns_existing_id(self, test_db):
        id1 = db.upsert_job(**self._job())
        id2 = db.upsert_job(**self._job())
        assert id1 == id2

    def test_different_url_inserts_new_row(self, test_db):
        id1 = db.upsert_job(**self._job(url='https://ziprecruiter.com/jobs/abc123'))
        id2 = db.upsert_job(**self._job(url='https://ziprecruiter.com/jobs/def456'))
        assert id1 != id2

    def test_manual_job_no_url_dedup_by_title_company(self, test_db):
        id1 = db.upsert_job(**self._job(url='', source='manual'))
        id2 = db.upsert_job(**self._job(url='', source='manual'))
        assert id1 == id2

    def test_manual_jobs_different_company_are_distinct(self, test_db):
        id1 = db.upsert_job(**self._job(url='', company='CompanyA'))
        id2 = db.upsert_job(**self._job(url='', company='CompanyB'))
        assert id1 != id2

    def test_none_url_treated_as_empty_string(self, test_db):
        id1 = db.upsert_job(**self._job(url=None))
        id2 = db.upsert_job(**self._job(url=None))
        assert id1 == id2


# ── upsert_analysis ───────────────────────────────────────────────────────────

class TestUpsertAnalysis:

    def _insert_job(self):
        return db.upsert_job(
            resume_type='test_resume', source='hybrid_scraper',
            title='SRE', company='Acme', location='Remote', salary=None,
            url='https://example.com/job1', description='desc', scraped_at='2026-01-01',
        )

    def test_insert_analysis(self, test_db):
        job_id = self._insert_job()
        db.upsert_analysis(job_id=job_id, decision='STRONG_MATCH', fit_score=0.85,
                           quick_checks={}, ai_analysis={'should_apply': 'DEFINITELY'})
        results = db.get_results()
        assert len(results) == 1
        assert results[0]['decision'] == 'STRONG_MATCH'
        assert abs(results[0]['fit_score'] - 0.85) < 0.001

    def test_upsert_overwrites_analysis(self, test_db):
        job_id = self._insert_job()
        db.upsert_analysis(job_id=job_id, decision='MAYBE', fit_score=0.4,
                           quick_checks={}, ai_analysis={})
        db.upsert_analysis(job_id=job_id, decision='STRONG_MATCH', fit_score=0.9,
                           quick_checks={}, ai_analysis={})
        results = db.get_results()
        assert len(results) == 1
        assert results[0]['decision'] == 'STRONG_MATCH'
        assert results[0]['fit_score'] > 0.8


# ── get_results ───────────────────────────────────────────────────────────────

class TestGetResults:

    def _add_job_with_analysis(self, resume_type, url, title, company, decision, score):
        job_id = db.upsert_job(
            resume_type=resume_type, source='hybrid_scraper',
            title=title, company=company, location='Remote', salary=None,
            url=url, description='desc', scraped_at='2026-01-01',
        )
        db.upsert_analysis(job_id=job_id, decision=decision, fit_score=score,
                           quick_checks={}, ai_analysis={})
        return job_id

    def test_returns_all_results(self, test_db):
        self._add_job_with_analysis('test_resume', 'https://example.com/1', 'SRE', 'Corp1', 'STRONG_MATCH', 0.9)
        self._add_job_with_analysis('test_resume', 'https://example.com/2', 'DevOps', 'Corp2', 'APPLY', 0.6)
        results = db.get_results()
        assert len(results) == 2

    def test_filters_by_resume_type(self, test_db):
        self._add_job_with_analysis('test_resume', 'https://example.com/1', 'SRE', 'Corp1', 'STRONG_MATCH', 0.9)
        self._add_job_with_analysis('am', 'https://example.com/2', 'AM Eng', 'Corp2', 'APPLY', 0.6)
        sre_results = db.get_results('test_resume')
        am_results = db.get_results('am')
        assert len(sre_results) == 1
        assert len(am_results) == 1
        assert sre_results[0]['job_metadata']['title'] == 'SRE'

    def test_sorted_by_fit_score_descending(self, test_db):
        self._add_job_with_analysis('test_resume', 'https://example.com/1', 'Low', 'Corp1', 'MAYBE', 0.3)
        self._add_job_with_analysis('test_resume', 'https://example.com/2', 'High', 'Corp2', 'STRONG_MATCH', 0.9)
        self._add_job_with_analysis('test_resume', 'https://example.com/3', 'Mid', 'Corp3', 'APPLY', 0.6)
        results = db.get_results()
        scores = [r['fit_score'] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_result_shape(self, test_db):
        job_id = self._add_job_with_analysis(
            'test_resume', 'https://example.com/1', 'SRE', 'TechCorp', 'STRONG_MATCH', 0.85)
        results = db.get_results()
        r = results[0]
        assert 'id' in r
        assert 'decision' in r
        assert 'fit_score' in r
        assert 'applied' in r
        assert 'job_metadata' in r
        assert r['job_metadata']['title'] == 'SRE'
        assert r['job_metadata']['company'] == 'TechCorp'

    def test_empty_db_returns_empty_list(self, test_db):
        assert db.get_results() == []

    def test_applied_flag_false_by_default(self, test_db):
        self._add_job_with_analysis('test_resume', 'https://example.com/1', 'SRE', 'Corp', 'APPLY', 0.6)
        results = db.get_results()
        assert results[0]['applied'] is False


# ── delete_job ────────────────────────────────────────────────────────────────

class TestDeleteJob:

    def test_delete_removes_job_and_analysis(self, test_db):
        job_id = db.upsert_job(
            resume_type='test_resume', source='hybrid_scraper',
            title='SRE', company='Corp', location='Remote', salary=None,
            url='https://example.com/j1', description='', scraped_at='2026-01-01',
        )
        db.upsert_analysis(job_id=job_id, decision='APPLY', fit_score=0.6,
                           quick_checks={}, ai_analysis={})
        assert len(db.get_results()) == 1
        db.delete_job(job_id)
        assert db.get_results() == []

    def test_delete_nonexistent_is_noop(self, test_db):
        db.delete_job(99999)  # should not raise


# ── set_applied ───────────────────────────────────────────────────────────────

class TestSetApplied:

    def _add_job(self):
        job_id = db.upsert_job(
            resume_type='test_resume', source='hybrid_scraper',
            title='SRE', company='Corp', location='Remote', salary=None,
            url='https://example.com/j1', description='', scraped_at='2026-01-01',
        )
        db.upsert_analysis(job_id=job_id, decision='APPLY', fit_score=0.6,
                           quick_checks={}, ai_analysis={})
        return job_id

    def test_mark_applied(self, test_db):
        job_id = self._add_job()
        db.set_applied(job_id, True)
        results = db.get_results()
        assert results[0]['applied'] is True

    def test_unmark_applied(self, test_db):
        job_id = self._add_job()
        db.set_applied(job_id, True)
        db.set_applied(job_id, False)
        results = db.get_results()
        assert results[0]['applied'] is False

    def test_double_apply_is_idempotent(self, test_db):
        job_id = self._add_job()
        db.set_applied(job_id, True)
        db.set_applied(job_id, True)  # should not raise
        results = db.get_results()
        assert results[0]['applied'] is True


# ── set_consider ───────────────────────────────────────────────────────────────

class TestSetConsider:

    def _add_analyzed_job(self, url='https://example.com/j1', decision='SKIP', score=0.30):
        job_id = db.upsert_job(
            resume_type='test_resume', source='hybrid_scraper',
            title='SRE', company='Corp', location='Remote', salary=None,
            url=url, description='', scraped_at='2026-01-01',
        )
        db.upsert_analysis(job_id=job_id, decision=decision, fit_score=score,
                           quick_checks={}, ai_analysis={})
        return job_id

    def test_sets_decision_to_consider(self, test_db):
        job_id = self._add_analyzed_job()
        db.set_consider(job_id, 0.30)
        results = db.get_results()
        assert results[0]['decision'] == 'CONSIDER'

    def test_sets_override_flag(self, test_db):
        job_id = self._add_analyzed_job()
        db.set_consider(job_id, 0.30)
        results = db.get_results()
        assert results[0]['override'] is True

    def test_stores_original_score(self, test_db):
        job_id = self._add_analyzed_job(score=0.35)
        db.set_consider(job_id, 0.35)
        results = db.get_results()
        assert abs(results[0]['override_from_score'] - 0.35) < 0.001

    def test_consider_preserved_through_reupsert(self, test_db):
        """Re-running upsert_analysis should NOT overwrite CONSIDER decision."""
        job_id = self._add_analyzed_job()
        db.set_consider(job_id, 0.30)
        db.upsert_analysis(job_id=job_id, decision='SKIP', fit_score=0.28,
                           quick_checks={}, ai_analysis={})
        results = db.get_results()
        assert results[0]['decision'] == 'CONSIDER'

    def test_double_consider_preserves_original_score(self, test_db):
        """Calling set_consider twice should not overwrite override_from_score."""
        job_id = self._add_analyzed_job(score=0.40)
        db.set_consider(job_id, 0.40)
        db.set_consider(job_id, 0.99)  # second call with bogus score
        results = db.get_results()
        assert abs(results[0]['override_from_score'] - 0.40) < 0.001


# ── get_all_jobs_for_resume ────────────────────────────────────────────────────

class TestGetAllJobsForResume:

    def _add_job(self, resume_type, url, title='SRE', company='Corp'):
        return db.upsert_job(
            resume_type=resume_type, source='hybrid_scraper',
            title=title, company=company, location='Remote', salary=None,
            url=url, description='desc', scraped_at='2026-01-01',
        )

    def test_returns_jobs_for_resume_type(self, test_db):
        self._add_job('test_resume', 'https://example.com/1')
        self._add_job('test_resume', 'https://example.com/2')
        self._add_job('am', 'https://example.com/3')
        jobs = db.get_all_jobs_for_resume('test_resume')
        assert len(jobs) == 2

    def test_empty_when_no_jobs(self, test_db):
        assert db.get_all_jobs_for_resume('test_resume') == []

    def test_returns_dicts_with_expected_keys(self, test_db):
        self._add_job('test_resume', 'https://example.com/1', title='Senior SRE', company='TechCorp')
        jobs = db.get_all_jobs_for_resume('test_resume')
        assert len(jobs) == 1
        assert jobs[0]['title'] == 'Senior SRE'
        assert jobs[0]['company'] == 'TechCorp'
        assert jobs[0]['resume_type'] == 'test_resume'

    def test_does_not_include_other_resume_types(self, test_db):
        self._add_job('am', 'https://example.com/am-1', title='AM Engineer')
        jobs = db.get_all_jobs_for_resume('test_resume')
        assert jobs == []


# ── get_jobs_by_ids ────────────────────────────────────────────────────────────

class TestGetJobsByIds:

    def _add_job(self, url, title='SRE', resume_type='test_resume'):
        return db.upsert_job(
            resume_type=resume_type, source='hybrid_scraper',
            title=title, company='Corp', location='Remote', salary=None,
            url=url, description='desc', scraped_at='2026-01-01',
        )

    def test_returns_matching_jobs(self, test_db):
        id1 = self._add_job('https://example.com/1', 'SRE')
        id2 = self._add_job('https://example.com/2', 'DevOps')
        self._add_job('https://example.com/3', 'AM Eng', resume_type='am')

        jobs = db.get_jobs_by_ids([id1, id2])
        assert len(jobs) == 2
        titles = {j['title'] for j in jobs}
        assert titles == {'SRE', 'DevOps'}

    def test_empty_list_returns_empty(self, test_db):
        assert db.get_jobs_by_ids([]) == []

    def test_nonexistent_ids_ignored(self, test_db):
        id1 = self._add_job('https://example.com/1')
        jobs = db.get_jobs_by_ids([id1, 99999, 88888])
        assert len(jobs) == 1

    def test_single_id(self, test_db):
        job_id = self._add_job('https://example.com/1', title='Platform Eng')
        jobs = db.get_jobs_by_ids([job_id])
        assert len(jobs) == 1
        assert jobs[0]['title'] == 'Platform Eng'


# ── resume CRUD ────────────────────────────────────────────────────────────────

class TestResumeCrud:

    def _criteria(self):
        return {'queries': [{'query': 'SRE', 'location': 'Portland'}], 'location_preferences': ['Portland']}

    def test_upsert_resume_insert(self, test_db):
        resume_id = db.upsert_resume('test_resume', '/resumes/test_resume/test_resume.txt', self._criteria())
        assert isinstance(resume_id, int)
        assert resume_id > 0

    def test_upsert_resume_update_on_conflict(self, test_db):
        id1 = db.upsert_resume('test_resume', '/resumes/test_resume/test_resume.txt', self._criteria())
        id2 = db.upsert_resume('test_resume', '/resumes/test_resume/test_resume.txt', {'queries': []})
        assert id1 == id2

    def test_get_resumes_list_returns_records(self, test_db):
        db.upsert_resume('test_resume', '/resumes/test_resume/test_resume.txt', self._criteria())
        db.upsert_resume('am', '/resumes/am/am.txt', None)
        resumes = db.get_resumes_list()
        assert len(resumes) == 2
        names = {r['name'] for r in resumes}
        assert names == {'test_resume', 'am'}

    def test_get_resumes_list_empty(self, test_db):
        assert db.get_resumes_list() == []

    def test_get_resume_by_id(self, test_db):
        resume_id = db.upsert_resume('test_resume', '/some/path.txt', self._criteria())
        resume = db.get_resume_by_id(resume_id)
        assert resume is not None
        assert resume['name'] == 'test_resume'
        assert resume['file_path'] == '/some/path.txt'

    def test_get_resume_by_id_missing_returns_none(self, test_db):
        assert db.get_resume_by_id(99999) is None

    def test_update_resume_criteria(self, test_db):
        resume_id = db.upsert_resume('test_resume', '/some/path.txt', self._criteria())
        new_criteria = {'queries': [{'query': 'DevOps', 'location': 'Remote'}]}
        result = db.update_resume_criteria(resume_id, new_criteria)
        assert result is True
        updated = db.get_resume_by_id(resume_id)
        assert updated['search_criteria']['queries'][0]['query'] == 'DevOps'

    def test_update_resume_criteria_nonexistent_returns_false(self, test_db):
        result = db.update_resume_criteria(99999, {})
        assert result is False

    def test_delete_resume_record_removes_resume(self, test_db):
        resume_id = db.upsert_resume('test_resume', '/some/path.txt', self._criteria())
        db.delete_resume_record(resume_id)
        assert db.get_resume_by_id(resume_id) is None

    def test_delete_resume_nonexistent_returns_zero(self, test_db):
        count = db.delete_resume_record(99999)
        assert count == 0

    def test_delete_resume_cascades_to_jobs(self, test_db):
        resume_id = db.upsert_resume('test_resume', '/some/path.txt', self._criteria())
        job_id = db.upsert_job(
            resume_type='test_resume', source='hybrid_scraper',
            title='SRE', company='Corp', location='Remote', salary=None,
            url='https://example.com/j1', description='', scraped_at='2026-01-01',
        )
        # Manually link job to resume
        import sqlite3
        import core.database as db_module
        with sqlite3.connect(str(db_module.DB_PATH)) as conn:
            conn.execute('UPDATE jobs SET resume_id=? WHERE id=?', (resume_id, job_id))

        count = db.delete_resume_record(resume_id)
        assert count == 1
        assert db.get_all_jobs_for_resume('test_resume') == []


# ── get_resume_queries ─────────────────────────────────────────────────────────

class TestGetResumeQueries:

    def test_returns_query_counts(self, test_db):
        resume_id = db.upsert_resume('test_resume', '/some/path.txt', {})
        # Insert jobs with search_query
        for url, sq in [
            ('https://example.com/1', 'SRE Portland'),
            ('https://example.com/2', 'SRE Portland'),
            ('https://example.com/3', 'DevOps Remote'),
        ]:
            job_id = db.upsert_job(
                resume_type='test_resume', source='hybrid_scraper',
                title='SRE', company='Corp', location='Remote', salary=None,
                url=url, description='', scraped_at='2026-01-01', search_query=sq,
            )
            import sqlite3
            import core.database as db_module
            with sqlite3.connect(str(db_module.DB_PATH)) as conn:
                conn.execute('UPDATE jobs SET resume_id=? WHERE id=?', (resume_id, job_id))

        queries = db.get_resume_queries(resume_id)
        assert len(queries) == 2
        top = queries[0]
        assert top['query'] == 'SRE Portland'
        assert top['count'] == 2

    def test_empty_when_no_jobs(self, test_db):
        resume_id = db.upsert_resume('test_resume', '/some/path.txt', {})
        assert db.get_resume_queries(resume_id) == []


# ── upsert_job search_query backfill ──────────────────────────────────────────

class TestUpsertJobSearchQueryBackfill:

    def test_backfills_null_search_query_on_conflict(self, test_db):
        # First insert: no search_query
        id1 = db.upsert_job(
            resume_type='test_resume', source='hybrid_scraper',
            title='SRE', company='Corp', location='Remote', salary=None,
            url='https://example.com/j1', description='', scraped_at='2026-01-01',
            search_query='',
        )
        # Second insert (conflict): provides search_query
        id2 = db.upsert_job(
            resume_type='test_resume', source='hybrid_scraper',
            title='SRE', company='Corp', location='Remote', salary=None,
            url='https://example.com/j1', description='', scraped_at='2026-01-01',
            search_query='SRE Portland',
        )
        assert id1 == id2
        jobs = db.get_all_jobs_for_resume('test_resume')
        assert jobs[0]['search_query'] == 'SRE Portland'

    def test_does_not_overwrite_existing_search_query(self, test_db):
        id1 = db.upsert_job(
            resume_type='test_resume', source='hybrid_scraper',
            title='SRE', company='Corp', location='Remote', salary=None,
            url='https://example.com/j1', description='', scraped_at='2026-01-01',
            search_query='Original Query',
        )
        db.upsert_job(
            resume_type='test_resume', source='hybrid_scraper',
            title='SRE', company='Corp', location='Remote', salary=None,
            url='https://example.com/j1', description='', scraped_at='2026-01-01',
            search_query='New Query',
        )
        jobs = db.get_all_jobs_for_resume('test_resume')
        assert jobs[0]['search_query'] == 'Original Query'
