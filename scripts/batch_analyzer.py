"""
Batch Job Analyzer - Process scraped jobs through ApplicationAgent
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.agent import analyze_job_fit
from core.database import init_db, upsert_job, upsert_analysis


def load_scraped_jobs(filepath):
    """Load jobs from scraper output JSON"""
    with open(filepath, 'r') as f:
        return json.load(f)


def load_resume(resume_path):
    """Load resume from path"""
    with open(resume_path, 'r') as f:
        return f.read()


def generate_pdf_report(result, output_dir=None):
    """Generate PDF report for a STRONG_MATCH job"""
    output_dir = output_dir or PROJECT_ROOT / 'output' / 'pdf'
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    job = result['job_metadata']

    company_clean = "".join(c if c.isalnum() or c in (' ', '-') else '_' for c in job['company'])
    title_clean = "".join(c if c.isalnum() or c in (' ', '-') else '_' for c in job['title'])
    filename = f"{company_clean}_{title_clean}.pdf".replace(' ', '_')[:100]
    filepath = output_path / filename

    doc = SimpleDocTemplate(str(filepath), pagesize=letter,
                            rightMargin=0.75*inch, leftMargin=0.75*inch,
                            topMargin=0.75*inch, bottomMargin=0.75*inch)

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'],
                                 fontSize=18, textColor='#1a1a1a',
                                 spaceAfter=12, alignment=TA_CENTER)
    company_style = ParagraphStyle('CompanyStyle', parent=styles['Heading2'],
                                   fontSize=14, textColor='#2c5aa0',
                                   spaceAfter=6, alignment=TA_CENTER)
    section_heading = ParagraphStyle('SectionHeading', parent=styles['Heading2'],
                                     fontSize=13, textColor='#1a1a1a',
                                     spaceBefore=12, spaceAfter=8)
    body_style = ParagraphStyle('BodyText', parent=styles['Normal'],
                                fontSize=11, leading=14, spaceAfter=6, leftIndent=12)

    story = []

    story.append(Paragraph(job['title'], title_style))
    story.append(Paragraph(job['company'], company_style))
    story.append(Spacer(1, 0.2*inch))

    meta_text = f"<b>Location:</b> {job['location']}"
    if job.get('salary'):
        meta_text += f" | <b>Salary:</b> {job['salary']}"
    story.append(Paragraph(meta_text, body_style))

    url_display = job['url'][:80] + "..." if len(job['url']) > 80 else job['url']
    story.append(Paragraph(f"<b>URL:</b> {url_display}", body_style))
    story.append(Spacer(1, 0.3*inch))

    story.append(Paragraph(f"<b>Fit Score:</b> {result['fit_score']:.2f} / 1.00", section_heading))

    decision_color = '#00aa00' if result['decision'] == 'STRONG_MATCH' else '#000000'
    story.append(Paragraph(f"<font color='{decision_color}'><b>Decision:</b> {result['decision']}</font>", body_style))
    story.append(Spacer(1, 0.2*inch))

    ats_pass = result.get('ai_analysis', {}).get('ats_pass_likelihood', 'UNKNOWN')
    ats_reasoning = result.get('ai_analysis', {}).get('ats_reasoning', '')
    ats_color = '#00aa00' if ats_pass == 'HIGH' else '#cc0000' if ats_pass == 'LOW' else '#ff9900'
    story.append(Paragraph(f"<font color='{ats_color}'><b>ATS Pass Likelihood:</b> {ats_pass}</font>", body_style))
    if ats_reasoning:
        story.append(Paragraph(ats_reasoning, body_style))
    story.append(Spacer(1, 0.2*inch))

    keyword_matches = result.get('ai_analysis', {}).get('keyword_matches', [])
    if keyword_matches:
        story.append(Paragraph("KEYWORD MATCHES (Strengths)", section_heading))
        story.append(Paragraph(", ".join(keyword_matches), body_style))
        story.append(Spacer(1, 0.2*inch))

    comp_strengths = result.get('ai_analysis', {}).get('competitive_strengths', [])
    if comp_strengths:
        story.append(Paragraph("COMPETITIVE STRENGTHS", section_heading))
        for strength in comp_strengths:
            story.append(Paragraph(f"• {strength}", body_style))
        story.append(Spacer(1, 0.2*inch))

    missing = result.get('ai_analysis', {}).get('missing_keywords', [])
    if missing:
        story.append(Paragraph("MISSING KEYWORDS (Gaps)", section_heading))
        story.append(Paragraph(", ".join(missing), body_style))
        story.append(Spacer(1, 0.2*inch))

    exp_level = result.get('ai_analysis', {}).get('experience_level', '')
    exp_reasoning = result.get('ai_analysis', {}).get('experience_reasoning', '')
    if exp_level or exp_reasoning:
        story.append(Paragraph("EXPERIENCE LEVEL", section_heading))
        if exp_level:
            story.append(Paragraph(f"<b>Assessment:</b> {exp_level}", body_style))
        if exp_reasoning:
            story.append(Paragraph(exp_reasoning, body_style))
        story.append(Spacer(1, 0.2*inch))

    role_fit = result.get('ai_analysis', {}).get('role_fit', '')
    role_fit_reasoning = result.get('ai_analysis', {}).get('role_fit_reasoning', '')
    if role_fit or role_fit_reasoning:
        story.append(Paragraph("ROLE FIT ANALYSIS", section_heading))
        if role_fit:
            fit_color = '#00aa00' if role_fit == 'EXCELLENT' else '#000000'
            story.append(Paragraph(f"<font color='{fit_color}'><b>Assessment:</b> {role_fit}</font>", body_style))
        if role_fit_reasoning:
            story.append(Paragraph(role_fit_reasoning, body_style))
        story.append(Spacer(1, 0.2*inch))

    comp_gaps = result.get('ai_analysis', {}).get('competitive_gaps', [])
    if comp_gaps:
        story.append(Paragraph("COMPETITIVE GAPS", section_heading))
        for gap in comp_gaps:
            story.append(Paragraph(f"• {gap}", body_style))
        story.append(Spacer(1, 0.2*inch))

    interview_warning = result.get('ai_analysis', {}).get('interview_warning', 'NONE')
    interview_red_flags = result.get('ai_analysis', {}).get('interview_red_flags', [])
    interview_reasoning = result.get('ai_analysis', {}).get('interview_reasoning', '')
    if interview_warning not in ('NONE', '', None) or interview_red_flags:
        warn_color = '#cc0000' if interview_warning == 'SEVERE' else '#ff9900' if interview_warning == 'MODERATE' else '#888888'
        story.append(Paragraph(f"<font color='{warn_color}'><b>INTERVIEW PROCESS WARNING: {interview_warning}</b></font>", section_heading))
        if interview_red_flags:
            for flag in interview_red_flags:
                story.append(Paragraph(f"• {flag}", body_style))
        if interview_reasoning:
            story.append(Paragraph(interview_reasoning, body_style))
        story.append(Spacer(1, 0.2*inch))

    app_strategy = result.get('ai_analysis', {}).get('application_strategy', '')
    if app_strategy:
        story.append(Paragraph("APPLICATION STRATEGY", section_heading))
        story.append(Paragraph(app_strategy, body_style))
        story.append(Spacer(1, 0.2*inch))

    overall_reasoning = result.get('ai_analysis', {}).get('overall_reasoning', '')
    if overall_reasoning:
        story.append(Paragraph("OVERALL REASONING", section_heading))
        story.append(Paragraph(overall_reasoning, body_style))
        story.append(Spacer(1, 0.2*inch))

    story.append(Spacer(1, 0.3*inch))
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=9, textColor='#666666')
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", footer_style))

    doc.build(story)
    return str(filepath)


def analyze_batch(jobs_file, resume_path, output_dir=None):
    """
    Analyze all jobs in a scraper output file. Results written to DB.

    Args:
        jobs_file: Path to scraper JSON output (data/<scraper>_<resume_type>_*.json)
        resume_path: Full path to resume text file
        output_dir: Unused — kept for API compatibility

    Returns:
        Number of jobs analyzed
    """
    init_db()

    print("="*70)
    print("BATCH JOB ANALYSIS")
    print("="*70)

    data = load_scraped_jobs(jobs_file)
    jobs = data['jobs']
    resume_type = data.get('resume_type', Path(resume_path).stem)
    resume = load_resume(resume_path)

    # Derive source: prefer JSON field, else strip _{resume_type}_{date} from filename
    _stem = Path(jobs_file).stem
    _marker = f'_{resume_type}_'
    _idx = _stem.find(_marker)
    source = data.get('source') or (_stem[:_idx] if _idx > 0 else _stem.split('_')[0])

    # Load location preferences from search criteria if available
    location_preferences = None
    criteria_path = PROJECT_ROOT / 'resumes' / resume_type / f'{resume_type}_search_criteria.json'
    if criteria_path.exists():
        with open(criteria_path) as f:
            criteria = json.load(f)
        location_preferences = criteria.get('location_preferences')

    print(f"Jobs to analyze: {len(jobs)}")
    print(f"Resume: {resume_path}")
    print(f"Scraped at: {data['scraped_at']}")
    print("="*70)

    results = []

    for i, job in enumerate(jobs):
        print(f"\n{'='*70}")
        print(f"JOB {i+1}/{len(jobs)}: {job['title']} at {job['company']}")
        print(f"{'='*70}")

        result = analyze_job_fit(
            job['description'],
            resume,
            resume_type,
            location_preferences=location_preferences
        )

        result['job_metadata'] = {
            'title': job['title'],
            'company': job['company'],
            'location': job['location'],
            'salary': job.get('salary'),
            'url': job['url'],
            'job_id': job.get('id'),
            'scraped_at': job.get('scraped_at')
        }

        # Write to DB
        job_id = upsert_job(
            resume_type=resume_type,
            source=source,
            title=job['title'],
            company=job['company'],
            location=job['location'],
            salary=job.get('salary'),
            url=job['url'],
            description=job['description'],
            scraped_at=job.get('scraped_at', ''),
            search_query=job.get('search_query', ''),
        )
        if job_id:
            upsert_analysis(
                job_id=job_id,
                decision=result['decision'],
                fit_score=result['fit_score'],
                quick_checks=result.get('quick_analysis', {}),
                ai_analysis=result.get('ai_analysis', {}),
            )

        results.append(result)

    results.sort(key=lambda x: x['fit_score'], reverse=True)

    # Generate PDFs for all jobs
    print(f"\n{'='*70}")
    print(f"GENERATING PDF REPORTS ({len(results)} jobs)")
    print(f"{'='*70}")
    for result in results:
        job = result['job_metadata']
        print(f"\n  [{result['decision']}] {job['title']} at {job['company']}")
        try:
            pdf_path = generate_pdf_report(result)
            print(f"  ✓ {pdf_path}")
        except Exception as e:
            print(f"  ✗ Error: {e}")

    print_summary(results)
    print(f"\nResults saved to DB ({len(results)} jobs)")
    return len(results)


def print_summary(results):
    """Print ranked summary of all jobs"""
    print("\n" + "="*70)
    print("RANKED RESULTS")
    print("="*70)

    groups = {
        'STRONG_MATCH': [r for r in results if r['decision'] == 'STRONG_MATCH'],
        'APPLY': [r for r in results if r['decision'] == 'APPLY'],
        'MAYBE': [r for r in results if r['decision'] == 'MAYBE'],
        'ATS_ONLY': [r for r in results if r['decision'] == 'ATS_ONLY'],
        'CONSIDER': [r for r in results if r['decision'] == 'CONSIDER'],
        'SKIP': [r for r in results if r['decision'] == 'SKIP'],
    }

    icons = {
        'STRONG_MATCH': '🎯',
        'APPLY': '✓',
        'MAYBE': '⚠️ ',
        'ATS_ONLY': '🤖',
        'CONSIDER': '🤔',
        'SKIP': '❌',
    }

    for decision, icon in icons.items():
        group = groups[decision]
        print(f"\n{icon} {decision} ({len(group)}):")
        for r in group:
            job = r['job_metadata']
            print(f"  {r['fit_score']:.2f} - {job['title']} at {job['company']}")
            if decision != 'SKIP':
                print(f"       {job['location']} | {job['url'][:60]}...")

    strong = len(groups['STRONG_MATCH'])
    apply = len(groups['APPLY'])
    skip = len(groups['MAYBE']) + len(groups['ATS_ONLY']) + len(groups['CONSIDER']) + len(groups['SKIP'])
    print(f"\n{'='*70}")
    print(f"Apply to: {strong} STRONG_MATCH + {apply} APPLY = {strong + apply} jobs")
    print(f"Skip: {skip} jobs")
    if strong:
        print(f"PDFs in: output/pdf/")
    print("="*70)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Batch job analyzer')
    parser.add_argument('jobs_file', help='Path to scraper output JSON (data/<scraper>_<resume_type>_*.json)')
    parser.add_argument('resume_path', help='Path to resume text file (e.g. resumes/<name>/<name>.txt)')
    parser.add_argument('--output-dir', default=None,
                        help='Output directory for analysis JSON (default: data/)')

    args = parser.parse_args()
    analyze_batch(args.jobs_file, args.resume_path, args.output_dir)


if __name__ == "__main__":
    main()
