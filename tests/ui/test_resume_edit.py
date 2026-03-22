from pathlib import Path
import pytest

pytestmark = pytest.mark.ui

FIXTURES_DIR = Path(__file__).parent.parent / 'fixtures'


def _upload_resume(page, name):
    """Helper: upload sample_resume.txt with a given name."""
    resume_file = FIXTURES_DIR / 'sample_resume.txt'
    page.click("text=+ Add New")
    page.fill("#upload-name", name)
    page.set_input_files("#upload-file", str(resume_file))
    page.fill(".q-keywords", "DevOps")
    page.fill(".q-location", "Portland OR")
    page.click("#upload-modal button:has-text('Upload')")
    page.wait_for_selector("#upload-modal", state="hidden", timeout=5000)


def test_gear_icon_opens_detail_view(page):
    """Gear icon on resume opens detail/edit view."""
    _upload_resume(page, "edit_test")
    page.click(".sidebar-gear")
    page.wait_for_selector("#resume-detail-view:not(.hidden)", timeout=3000)


def test_edit_resume_save_queries(page):
    """Save Queries button updates search criteria."""
    _upload_resume(page, "query_test")
    page.click(".sidebar-gear")
    page.wait_for_selector("#resume-detail-view:not(.hidden)")

    page.fill(".detail-query-keywords", "Platform Engineer")
    page.click("button:has-text('Save Queries')")

    page.locator("[id^='detail-queries-msg']").wait_for(state="visible", timeout=3000)


def test_edit_resume_save_exclusions(page):
    """Save Exclusions updates exclude keywords."""
    _upload_resume(page, "excl_test")
    page.click(".sidebar-gear")
    page.wait_for_selector("#resume-detail-view:not(.hidden)")

    page.fill(".detail-textarea", "Junior\nIntern\nClearance")
    page.click("button:has-text('Save Exclusions')")
    page.locator("[id^='detail-excludes-msg']").wait_for(state="visible", timeout=3000)


def test_delete_resume(page):
    """Delete button removes resume from sidebar."""
    _upload_resume(page, "delete_test")
    page.click(".sidebar-gear")
    page.wait_for_selector("#resume-detail-view:not(.hidden)")

    page.click("button.btn-danger:has-text('Delete')")
    # Confirm in the confirmation modal
    page.locator("button.btn-danger:has-text('Delete')").last.click()
    page.wait_for_selector("text=delete_test", state="hidden", timeout=3000)
