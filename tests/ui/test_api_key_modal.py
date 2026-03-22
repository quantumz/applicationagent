import pytest

pytestmark = pytest.mark.ui


def test_settings_modal_opens(page):
    """Settings button opens the API key modal."""
    page.click(".settings-btn")
    assert page.is_visible("#settings-modal:not(.hidden)")


def test_settings_modal_has_key_input(page):
    """Modal has an API key input field."""
    page.click(".settings-btn")
    assert page.is_visible("#settings-api-key")


def test_invalid_key_shows_error(page):
    """Non sk-ant- key is rejected — modal stays open."""
    page.click(".settings-btn")
    page.fill("#settings-api-key", "not-a-valid-key")
    page.click("button:has-text('Save Key')")
    page.wait_for_timeout(500)
    # Modal should still be open on validation error
    assert page.is_visible("#settings-modal:not(.hidden)")


def test_status_endpoint_reports_key_configured(page):
    """API returns api_key_configured: true after conftest seeds the key."""
    response = page.request.get("http://localhost:8081/api/settings/status")
    data = response.json()
    assert data.get("api_key_configured") is True
