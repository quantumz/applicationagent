import json
import pytest

pytestmark = pytest.mark.ui


def test_run_button_visible(page):
    """Run button is present on the main page."""
    assert page.is_visible("#run-btn")


def test_run_modal_opens(page):
    """Clicking Run opens the run modal."""
    page.click("#run-btn")
    assert page.is_visible(".modal:visible")


def test_run_modal_has_resume_selector(page):
    """Run modal contains resume type selector."""
    page.click("#run-btn")
    assert page.is_visible("select") or page.is_visible("[data-resume]")


def test_run_endpoint_opens_sse_stream(page, flask_server):
    """
    /api/run returns 200 with text/event-stream for analyze-only mode.
    Verifies the endpoint accepts the request and starts streaming.
    Does NOT wait for analysis to complete — no live API calls made by this test.
    The subprocess runs with a fake key and will fail internally, but Flask
    opens the SSE stream before the subprocess result is known.
    """
    scraped_dir = flask_server / 'data' / 'scraped'
    scraped_dir.mkdir(parents=True, exist_ok=True)
    fixture = {
        "scraped_at": "2026-03-18T10:00:00",
        "source": "hybrid_scraper",
        "resume_type": "test_sre",
        "total_jobs": 1,
        "jobs": [{
            "id": "test-001",
            "title": "Senior SRE",
            "company": "TestCorp",
            "location": "Portland, OR",
            "salary": "$150k",
            "url": "https://example.com/job/1",
            "description": "Build and operate Kubernetes infrastructure.",
            "scraped_at": "2026-03-18T10:00:00",
            "search_query": "SRE Portland OR"
        }]
    }
    (scraped_dir / 'hybrid_scraper_test_sre_2026-03-18.json').write_text(
        json.dumps(fixture)
    )

    response = page.request.get(
        'http://localhost:8081/api/run?resume_type=test_sre&mode=analyze'
        '&data_file=hybrid_scraper_test_sre_2026-03-18.json'
        '&reset_cache=false&scraper=hybrid_scraper'
    )
    assert response.status == 200
    assert 'text/event-stream' in response.headers.get('content-type', '')
