from pathlib import Path
import pytest

pytestmark = pytest.mark.ui

FIXTURES_DIR = Path(__file__).parent.parent / 'fixtures'


def test_add_resume_opens_modal(page):
    """+ Add New button opens the Add Resume modal."""
    page.click("text=+ Add New")
    assert page.is_visible("#upload-modal:not(.hidden)")


def test_add_resume_modal_has_required_fields(page):
    """Modal has name, file, query, and upload button."""
    page.click("text=+ Add New")
    assert page.is_visible("#upload-name")
    assert page.is_visible("#upload-file")
    assert page.is_visible("#upload-modal button:has-text('Upload')")


def test_add_resume_txt_upload_succeeds(page):
    """Upload a .txt resume — modal closes, sidebar shows name, API confirms it's stored."""
    resume_file = FIXTURES_DIR / 'sample_resume.txt'

    page.click("text=+ Add New")
    page.fill("#upload-name", "test_sre")
    page.set_input_files("#upload-file", str(resume_file))
    page.fill(".q-keywords", "Site Reliability Engineer")
    page.fill(".q-location", "Portland OR")
    page.click("#upload-modal button:has-text('Upload')")

    # UI: modal closes and resume name appears in sidebar
    page.wait_for_selector("#upload-modal", state="hidden", timeout=5000)
    assert page.is_visible("text=test_sre")

    # Backend: resume is present in /api/resumes with correct name and non-zero word count
    response = page.request.get("http://localhost:8081/api/resumes")
    assert response.status == 200
    resumes = response.json()["resumes"]
    names = [r["name"] for r in resumes]
    assert "test_sre" in names, f"test_sre not found in API response: {names}"
    resume = next(r for r in resumes if r["name"] == "test_sre")
    assert resume["word_count"] > 0, "Resume uploaded but word count is 0 — file not stored"


def test_add_resume_pdf_upload_succeeds(page, tmp_path):
    """Upload a .pdf resume — modal closes, sidebar shows name, API confirms text extracted."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import LETTER

    # Build a minimal PDF from the sample resume text
    pdf_path = tmp_path / "test_resume.pdf"
    resume_text = (FIXTURES_DIR / 'sample_resume.txt').read_text()
    c = canvas.Canvas(str(pdf_path), pagesize=LETTER)
    y = 750
    for line in resume_text.splitlines():
        c.drawString(40, y, line[:100])
        y -= 14
        if y < 50:
            c.showPage()
            y = 750
    c.save()

    page.click("text=+ Add New")
    page.fill("#upload-name", "test_sre_pdf")
    page.set_input_files("#upload-file", str(pdf_path))
    page.fill(".q-keywords", "Site Reliability Engineer")
    page.fill(".q-location", "Portland OR")
    page.click("#upload-modal button:has-text('Upload')")

    # UI: modal closes and resume name appears in sidebar
    page.wait_for_selector("#upload-modal", state="hidden", timeout=5000)
    assert page.is_visible("text=test_sre_pdf")

    # Backend: PDF text was extracted — word count must be non-zero
    response = page.request.get("http://localhost:8081/api/resumes")
    assert response.status == 200
    resumes = response.json()["resumes"]
    names = [r["name"] for r in resumes]
    assert "test_sre_pdf" in names, f"test_sre_pdf not found in API response: {names}"
    resume = next(r for r in resumes if r["name"] == "test_sre_pdf")
    assert resume["word_count"] > 0, "PDF uploaded but word count is 0 — text extraction failed"


def test_add_resume_validation_empty_name(page):
    """Empty name shows error, does not submit."""
    page.click("text=+ Add New")
    page.click("#upload-modal button:has-text('Upload')")
    assert page.is_visible("#upload-error")
    assert "required" in page.text_content("#upload-error").lower()


def test_add_resume_validation_no_query(page):
    """No search query shows error."""
    resume_file = FIXTURES_DIR / 'sample_resume.txt'

    page.click("text=+ Add New")
    page.fill("#upload-name", "no_query_test")
    page.set_input_files("#upload-file", str(resume_file))
    page.click(".remove-btn")
    page.click("#upload-modal button:has-text('Upload')")
    assert page.is_visible("#upload-error")
