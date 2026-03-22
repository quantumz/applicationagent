#!/usr/bin/env python3
"""
Generate a PDF test report from a pytest run.

Usage:
    python scripts/test_report.py [pytest args]

Examples:
    python scripts/test_report.py
    python scripts/test_report.py tests/ui -m ui
    python scripts/test_report.py tests/test_agent.py -v

Output: tests/output/pdf/test_report_YYYY-MM-DD_HHMMSS.pdf
"""

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / 'tests' / 'output' / 'pdf'

# ── Color palette ──────────────────────────────────────────────────────────────
GREEN  = colors.HexColor('#2d7a2d')
RED    = colors.HexColor('#b22222')
YELLOW = colors.HexColor('#b8860b')
GREY   = colors.HexColor('#555555')
LIGHT_GREEN = colors.HexColor('#e8f5e9')
LIGHT_RED   = colors.HexColor('#fdecea')
LIGHT_GREY  = colors.HexColor('#f5f5f5')
DARK_BG     = colors.HexColor('#1e1e1e')


def run_pytest(pytest_args):
    """Run pytest and return (stdout, returncode)."""
    cmd = [sys.executable, '-m', 'pytest', '--tb=short', '-v'] + pytest_args
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    return result.stdout + result.stderr, result.returncode


def parse_results(output):
    """Parse pytest -v output into structured results."""
    tests = []
    failures = {}
    current_failure_name = None
    in_failure_block = False

    for line in output.splitlines():
        # Test result lines: path::TestClass::test_name PASSED/FAILED/ERROR/SKIPPED
        match = re.match(r'^(tests/\S+)\s+(PASSED|FAILED|ERROR|SKIPPED)\s*(\[.*?\])?', line)
        if match:
            name = match.group(1)
            status = match.group(2)
            tests.append({'name': name, 'status': status})
            if status in ('FAILED', 'ERROR'):
                current_failure_name = name
                failures[current_failure_name] = []
            in_failure_block = False
            continue

        # Capture failure details
        if line.startswith('FAILED ') or line.startswith('ERROR '):
            in_failure_block = False

        if re.match(r'^_{5,}', line):
            in_failure_block = False

        if current_failure_name and line.startswith('_' * 5):
            in_failure_block = True
            continue

        if in_failure_block and current_failure_name:
            failures[current_failure_name].append(line)

    # Summary line: "5 failed, 10 passed in 3.2s"
    summary = {}
    summary_match = re.search(
        r'(\d+) failed|(\d+) passed|(\d+) error|(\d+) skipped|(\d+\.\d+)s',
        output
    )
    for key, pattern in [('failed', r'(\d+) failed'), ('passed', r'(\d+) passed'),
                          ('errors', r'(\d+) error'), ('skipped', r'(\d+) skipped'),
                          ('duration', r'([\d.]+)s$')]:
        m = re.search(pattern, output, re.MULTILINE)
        if m:
            summary[key] = m.group(1)

    return tests, failures, summary


def build_pdf(output, tests, failures, summary, returncode, pytest_args, out_path):
    """Render the PDF report."""
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    story = []

    # ── Title ──────────────────────────────────────────────────────────────────
    title_style = ParagraphStyle(
        'Title', parent=styles['Title'],
        fontSize=20, textColor=DARK_BG, spaceAfter=4,
    )
    sub_style = ParagraphStyle(
        'Sub', parent=styles['Normal'],
        fontSize=9, textColor=GREY, spaceAfter=2,
    )
    story.append(Paragraph("ApplicationAgent — Test Report", title_style))
    story.append(Paragraph(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sub_style))
    cmd_str = 'pytest ' + ' '.join(pytest_args) if pytest_args else 'pytest (all tests)'
    story.append(Paragraph(f"Command: {cmd_str}", sub_style))
    story.append(HRFlowable(width="100%", thickness=1, color=GREY, spaceAfter=12))

    # ── Summary banner ─────────────────────────────────────────────────────────
    passed  = int(summary.get('passed',  0))
    failed  = int(summary.get('failed',  0))
    errors  = int(summary.get('errors',  0))
    skipped = int(summary.get('skipped', 0))
    total   = passed + failed + errors + skipped
    duration = summary.get('duration', '?')
    overall = 'PASS' if returncode == 0 else 'FAIL'
    overall_color = GREEN if returncode == 0 else RED
    overall_bg = LIGHT_GREEN if returncode == 0 else LIGHT_RED

    banner_style = ParagraphStyle('Banner', parent=styles['Normal'], fontSize=13,
                                  textColor=overall_color, leading=16)
    stat_style   = ParagraphStyle('Stat',   parent=styles['Normal'], fontSize=10,
                                  textColor=GREY)

    banner_data = [[
        Paragraph(f"<b>Result: {overall}</b>", banner_style),
        Paragraph(f"<b>{passed}</b> passed", ParagraphStyle('P', parent=styles['Normal'], fontSize=10, textColor=GREEN)),
        Paragraph(f"<b>{failed + errors}</b> failed", ParagraphStyle('F', parent=styles['Normal'], fontSize=10, textColor=RED if (failed + errors) else GREY)),
        Paragraph(f"<b>{skipped}</b> skipped", ParagraphStyle('S', parent=styles['Normal'], fontSize=10, textColor=YELLOW if skipped else GREY)),
        Paragraph(f"<b>{total}</b> total  ·  {duration}s", stat_style),
    ]]
    banner_table = Table(banner_data, colWidths=[1.5*inch, 1*inch, 1*inch, 1*inch, 2*inch])
    banner_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), overall_bg),
        ('BOX',        (0,0), (-1,-1), 0.5, overall_color),
        ('VALIGN',     (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(banner_table)
    story.append(Spacer(1, 14))

    # ── Test results table ─────────────────────────────────────────────────────
    heading_style = ParagraphStyle('Heading', parent=styles['Normal'], fontSize=11,
                                   textColor=DARK_BG, spaceBefore=6, spaceAfter=4)
    story.append(Paragraph("<b>Test Results</b>", heading_style))

    STATUS_COLOR = {'PASSED': GREEN, 'FAILED': RED, 'ERROR': RED, 'SKIPPED': YELLOW}
    name_style = ParagraphStyle('TName', parent=styles['Normal'], fontSize=7.5,
                                 fontName='Courier', textColor=DARK_BG)
    rows = [['Status', 'Test']]
    row_styles = [
        ('BACKGROUND', (0,0), (-1,0), DARK_BG),
        ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
        ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE',   (0,0), (-1,0), 9),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('TOPPADDING',    (0,0), (-1,0), 6),
        ('GRID', (0,0), (-1,-1), 0.25, colors.HexColor('#cccccc')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]

    for i, t in enumerate(tests, start=1):
        status = t['status']
        sc = STATUS_COLOR.get(status, GREY)
        status_para = Paragraph(
            f'<font color="{sc.hexval()}"><b>{status}</b></font>',
            ParagraphStyle('S', parent=styles['Normal'], fontSize=8, alignment=1)
        )
        rows.append([status_para, Paragraph(t['name'], name_style)])
        bg = LIGHT_RED if status in ('FAILED', 'ERROR') else (LIGHT_GREEN if status == 'PASSED' else LIGHT_GREY)
        row_styles.append(('BACKGROUND', (0,i), (-1,i), bg))
        row_styles.append(('TOPPADDING', (0,i), (-1,i), 3))
        row_styles.append(('BOTTOMPADDING', (0,i), (-1,i), 3))

    results_table = Table(rows, colWidths=[0.8*inch, 6.2*inch])
    results_table.setStyle(TableStyle(row_styles))
    story.append(results_table)

    # ── Failure details ────────────────────────────────────────────────────────
    if failures:
        story.append(Spacer(1, 16))
        story.append(Paragraph("<b>Failure Details</b>", heading_style))
        code_style = ParagraphStyle('Code', parent=styles['Normal'], fontSize=7,
                                    fontName='Courier', textColor=DARK_BG,
                                    leading=10, leftIndent=8)
        fail_name_style = ParagraphStyle('FN', parent=styles['Normal'], fontSize=8,
                                          textColor=RED, fontName='Helvetica-Bold',
                                          spaceBefore=8, spaceAfter=2)
        for name, lines in failures.items():
            story.append(Paragraph(name, fail_name_style))
            block_lines = [l for l in lines if l.strip()]
            if block_lines:
                content = '\n'.join(block_lines[:60])  # cap at 60 lines per failure
                story.append(Paragraph(content.replace('\n', '<br/>').replace(' ', '&nbsp;'), code_style))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#dddddd')))

    # ── Uploaded resume content (when upload test passed) ──────────────────────
    upload_test = 'tests/ui/test_resume_upload.py::test_add_resume_txt_upload_succeeds'
    upload_result = next((t for t in tests if t['name'] == upload_test), None)
    if upload_result and upload_result['status'] == 'PASSED':
        resume_path = PROJECT_ROOT / 'tests' / 'fixtures' / 'sample_resume.txt'
        if resume_path.exists():
            story.append(Spacer(1, 16))
            story.append(Paragraph("<b>Uploaded Resume Content</b>", heading_style))
            story.append(Paragraph(
                f"File: <font name='Courier'>{resume_path.relative_to(PROJECT_ROOT)}</font>",
                ParagraphStyle('FP', parent=styles['Normal'], fontSize=8, textColor=GREY, spaceAfter=4)
            ))
            resume_text = resume_path.read_text()
            resume_style = ParagraphStyle(
                'Resume', parent=styles['Normal'], fontSize=8,
                fontName='Courier', textColor=DARK_BG, leading=11,
                leftIndent=8, borderPadding=8,
            )
            safe = resume_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            story.append(Table(
                [[Paragraph(safe.replace('\n', '<br/>').replace(' ', '&nbsp;'), resume_style)]],
                colWidths=[7*inch],
                style=TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), LIGHT_GREY),
                    ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#cccccc')),
                    ('TOPPADDING', (0,0), (-1,-1), 8),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 8),
                    ('LEFTPADDING', (0,0), (-1,-1), 8),
                ])
            ))

    # ── Live API results (if sidecar present) ─────────────────────────────────
    live_result_path = PROJECT_ROOT / 'tests' / 'output' / 'live_api_result.json'
    live_test = 'tests/integration/test_live_api.py::test_live_analyze_job_fit'
    live_ran = next((t for t in tests if t['name'] == live_test), None)
    if live_ran and live_ran['status'] == 'PASSED' and live_result_path.exists():
        import json as _json
        lr = _json.loads(live_result_path.read_text())
        ai = lr.get('ai_analysis', {})
        req = lr.get('request', {})
        raw = lr.get('response_raw', {})
        res = lr.get('result', {})
        qa  = lr.get('quick_analysis', {})

        story.append(Spacer(1, 16))
        story.append(HRFlowable(width="100%", thickness=1, color=GREEN, spaceAfter=8))
        story.append(Paragraph("<b>Live API Smoke Test — Full Results</b>", heading_style))

        def kv_table(rows_data, col_widths=(2.2*inch, 4.8*inch)):
            t = Table(rows_data, colWidths=col_widths)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (0,-1), LIGHT_GREY),
                ('FONTNAME',   (0,0), (0,-1), 'Helvetica-Bold'),
                ('FONTSIZE',   (0,0), (-1,-1), 8),
                ('GRID',       (0,0), (-1,-1), 0.25, colors.HexColor('#cccccc')),
                ('VALIGN',     (0,0), (-1,-1), 'TOP'),
                ('TOPPADDING', (0,0), (-1,-1), 4),
                ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ('LEFTPADDING',   (0,0), (-1,-1), 6),
            ]))
            return t

        sub = ParagraphStyle('Sub', parent=styles['Normal'], fontSize=9,
                             textColor=DARK_BG, fontName='Helvetica-Bold',
                             spaceBefore=10, spaceAfter=3)
        val = ParagraphStyle('Val', parent=styles['Normal'], fontSize=8, textColor=DARK_BG)

        # Auth + request
        story.append(Paragraph("Authentication &amp; Request", sub))
        story.append(kv_table([
            ['Timestamp',     lr.get('timestamp', '')],
            ['API Key',       lr.get('key_preview', '')],
            ['Auth Status',   lr.get('auth_status', '')],
            ['Model sent',    req.get('model', '')],
            ['Max tokens',    str(req.get('max_tokens', ''))],
            ['Prompt size',   f"{req.get('prompt_chars', 0):,} chars"],
        ]))

        # Response envelope
        story.append(Paragraph("Response Envelope", sub))
        story.append(kv_table([
            ['Response ID',    raw.get('id', '')],
            ['Model served',   raw.get('model', '')],
            ['Stop reason',    raw.get('stop_reason', '')],
            ['Input tokens',   f"{raw.get('input_tokens', 0):,}"],
            ['Output tokens',  f"{raw.get('output_tokens', 0):,}"],
            ['Response size',  f"{raw.get('response_chars', 0):,} chars"],
            ['Latency',        f"{lr.get('elapsed_s', '?')}s"],
            ['Est. cost',      f"${lr.get('cost_usd', '?')}"],
        ]))

        # Decision
        decision_color = GREEN if res.get('decision') in ('STRONG_MATCH', 'APPLY') else \
                         YELLOW if res.get('decision') in ('MAYBE', 'ATS_ONLY') else RED
        story.append(Paragraph("Analysis Decision", sub))
        story.append(kv_table([
            ['Decision',    Paragraph(f'<font color="{decision_color.hexval()}"><b>{res.get("decision")}</b></font>', val)],
            ['Fit score',   f"{res.get('fit_score', 0):.2f} / 1.00"],
            ['Resume type', res.get('resume_type', '')],
            ['Should apply',      ai.get('should_apply', '')],
            ['ATS likelihood',    ai.get('ats_pass_likelihood', '')],
            ['Experience level',  ai.get('experience_level', '')],
            ['Role fit',          ai.get('role_fit', '')],
            ['Interview warning', ai.get('interview_warning', '')],
            ['Confidence',        f"{float(ai.get('confidence', 0)):.0%}"],
        ]))

        # Quick checks
        story.append(Paragraph("Quick Checks (pre-API)", sub))
        story.append(kv_table([
            ['Title match',        '✓' if qa.get('title_match') else '✗'],
            ['Senior level',       '✓' if qa.get('senior_level_match') else '✗'],
            ['Location compatible','✓' if qa.get('location_compatible') else '✗'],
            ['Dealbreakers',       ', '.join(qa.get('obvious_dealbreakers', [])) or 'None'],
        ]))

        # Keywords
        story.append(Paragraph("Keyword Analysis", sub))
        matched  = ', '.join(ai.get('keyword_matches', [])) or 'None'
        missing  = ', '.join(ai.get('missing_keywords', [])) or 'None'
        story.append(kv_table([
            ['Matched keywords', Paragraph(matched, val)],
            ['Missing keywords', Paragraph(missing, val)],
        ]))

        # Strengths / gaps
        story.append(Paragraph("Competitive Assessment", sub))
        strengths = '\n'.join(f"• {s}" for s in ai.get('competitive_strengths', [])) or 'None'
        gaps      = '\n'.join(f"• {g}" for g in ai.get('competitive_gaps', [])) or 'None'
        story.append(kv_table([
            ['Strengths', Paragraph(strengths.replace('\n','<br/>'), val)],
            ['Gaps',      Paragraph(gaps.replace('\n','<br/>'), val)],
        ]))

        # Reasoning
        story.append(Paragraph("Reasoning &amp; Strategy", sub))
        story.append(kv_table([
            ['ATS reasoning',        Paragraph(ai.get('ats_reasoning', ''), val)],
            ['Role fit reasoning',   Paragraph(ai.get('role_fit_reasoning', ''), val)],
            ['Experience reasoning', Paragraph(ai.get('experience_reasoning', ''), val)],
            ['Application strategy', Paragraph(ai.get('application_strategy', ''), val)],
            ['Overall reasoning',    Paragraph(ai.get('overall_reasoning', ''), val)],
        ]))

        # Job description used
        story.append(Paragraph("Job Description Used", sub))
        jd_safe = lr.get('job_description', '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
        story.append(Table(
            [[Paragraph(jd_safe, ParagraphStyle('JD', parent=styles['Normal'], fontSize=8,
                                                 fontName='Courier', textColor=DARK_BG, leading=11))]],
            colWidths=[7*inch],
            style=TableStyle([
                ('BACKGROUND',    (0,0),(-1,-1), LIGHT_GREY),
                ('BOX',           (0,0),(-1,-1), 0.5, colors.HexColor('#cccccc')),
                ('TOPPADDING',    (0,0),(-1,-1), 6),
                ('BOTTOMPADDING', (0,0),(-1,-1), 6),
                ('LEFTPADDING',   (0,0),(-1,-1), 8),
            ])
        ))
        story.append(HRFlowable(width="100%", thickness=1, color=GREEN, spaceBefore=12, spaceAfter=4))

    # ── Raw output (full) ──────────────────────────────────────────────────────
    story.append(Spacer(1, 16))
    story.append(Paragraph("<b>Raw Output</b>", heading_style))
    raw_style = ParagraphStyle('Raw', parent=styles['Normal'], fontSize=6.5,
                                fontName='Courier', textColor=DARK_BG, leading=9)
    raw_text = output.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    story.append(Paragraph(raw_text.replace('\n', '<br/>').replace(' ', '&nbsp;'), raw_style))

    doc.build(story)


def main():
    pytest_args = sys.argv[1:]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    out_path = OUTPUT_DIR / f'test_report_{timestamp}.pdf'

    output, returncode = run_pytest(pytest_args)
    tests, failures, summary = parse_results(output)
    build_pdf(output, tests, failures, summary, returncode, pytest_args, out_path)

    passed  = int(summary.get('passed', 0))
    failed  = int(summary.get('failed', 0))
    errors  = int(summary.get('errors', 0))
    result  = 'PASS' if returncode == 0 else 'FAIL'
    print(f"\n[{result}] {passed} passed, {failed + errors} failed → {out_path}")
    sys.exit(returncode)


if __name__ == '__main__':
    main()
