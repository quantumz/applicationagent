"""
Playwright tests for the forge modal (openForgeModal / forge_complete SSE handler).

All tests call openForgeModal() directly via page.evaluate() — no STRONG_MATCH
seed data required.
"""

import pytest

pytestmark = pytest.mark.ui


def test_modal_creates_element(page):
    """openForgeModal() appends #forge-modal to the DOM."""
    page.evaluate("openForgeModal(42)")
    assert page.is_visible("#forge-modal")


def test_modal_iframe_src(page):
    """iframe src is pointed at RF with the correct job_id query param."""
    page.evaluate("openForgeModal(42)")
    src = page.evaluate(
        "document.querySelector('#forge-modal iframe').src"
    )
    assert src == "http://localhost:8091/?job_id=42"


def test_modal_close_button_removes_it(page):
    """Clicking [ close ] removes the modal from the DOM."""
    page.evaluate("openForgeModal(42)")
    assert page.is_visible("#forge-modal")
    page.click("#forge-modal button")
    assert not page.query_selector("#forge-modal")


def test_modal_has_job_id_data_attr(page):
    """Modal carries data-job-id so the SSE handler can match it."""
    page.evaluate("openForgeModal(99)")
    job_id = page.evaluate(
        "document.getElementById('forge-modal').dataset.jobId"
    )
    assert job_id == "99"


def test_double_open_replaces_existing_modal(page):
    """Opening a second modal removes the first — no stacked modals."""
    page.evaluate("openForgeModal(1)")
    page.evaluate("openForgeModal(2)")
    modals = page.query_selector_all("#forge-modal")
    assert len(modals) == 1
    job_id = page.evaluate(
        "document.getElementById('forge-modal').dataset.jobId"
    )
    assert job_id == "2"
