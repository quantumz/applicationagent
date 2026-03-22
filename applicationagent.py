#!/usr/bin/env python3
"""
ApplicationAgent - Job Search Automation
Single entry point: scrape → analyze → track

Usage:
  python applicationagent.py <resume_type>
  python applicationagent.py <resume_type> --scrape-only
  python applicationagent.py <resume_type> --analyze-only data/scraped/<scraper>_<resume_type>_YYYY-MM-DD.json
  python applicationagent.py <resume_type> --reset-cache
  python applicationagent.py <resume_type> --reanalyze
  python applicationagent.py <resume_type> --scraper hybrid_scraper
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent


def reanalyze_jobs(resume_type, job_ids=None):
    """Re-analyze existing jobs from DB with current scoring logic. No scraping."""
    import core.database as db
    from core.agent import analyze_job_fit

    resume_path = PROJECT_ROOT / 'resumes' / resume_type / f'{resume_type}.txt'
    if not resume_path.exists():
        print(f"ERROR: Resume not found at {resume_path}")
        sys.exit(1)
    resume_text = resume_path.read_text()

    location_preferences = None
    criteria_path = PROJECT_ROOT / 'resumes' / resume_type / f'{resume_type}_search_criteria.json'
    if criteria_path.exists():
        criteria = json.loads(criteria_path.read_text())
        location_preferences = criteria.get('location_preferences')

    if job_ids:
        jobs = db.get_jobs_by_ids(job_ids)
        if len(jobs) != len(job_ids):
            found_ids = {j['id'] for j in jobs}
            missing = set(job_ids) - found_ids
            print(f"WARNING: Could not find job IDs: {missing}")
        print(f"Re-analyzing {len(jobs)} selected jobs...")
    else:
        jobs = db.get_all_jobs_for_resume(resume_type)
        print(f"Re-analyzing ALL jobs for {resume_type} ({len(jobs)} jobs)...")

    if not jobs:
        print("No jobs found to re-analyze.")
        return

    success_count = 0
    error_count = 0

    for i, job in enumerate(jobs, 1):
        print(f"[{i}/{len(jobs)}] {job['title']} @ {job['company']}")
        try:
            result = analyze_job_fit(
                job_description=job['description'],
                resume_text=resume_text,
                resume_type=resume_type,
                location_preferences=location_preferences,
            )
            db.upsert_analysis(
                job_id=job['id'],
                decision=result['decision'],
                fit_score=result['fit_score'],
                quick_checks=result['quick_analysis'],
                ai_analysis=result['ai_analysis'],
            )
            result['job_metadata'] = {
                'title': job['title'], 'company': job['company'],
                'location': job.get('location', ''), 'salary': job.get('salary'),
                'url': job.get('url', ''), 'scraped_at': job.get('scraped_at', ''),
            }
            from scripts.batch_analyzer import generate_pdf_report
            generate_pdf_report(result, output_dir=str(PROJECT_ROOT / 'output' / 'pdf'))
            success_count += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            error_count += 1

    print(f"\n{'='*60}")
    print(f"Re-analysis complete!")
    print(f"  Success: {success_count}")
    print(f"  Errors:  {error_count}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description='ApplicationAgent - Automated job search and fit analysis',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python applicationagent.py <resume_type>
  python applicationagent.py <resume_type> --scrape-only
  python applicationagent.py <resume_type> --analyze-only data/scraped/<scraper>_<resume_type>_YYYY-MM-DD.json
  python applicationagent.py <resume_type> --reset-cache
  python applicationagent.py <resume_type> --reanalyze
        """
    )

    parser.add_argument('resume_type',
                        help='Resume type to use (must match a folder in resumes/)')
    parser.add_argument('--scrape-only', action='store_true',
                        help='Scrape jobs and stop (skip analysis and tracking)')
    parser.add_argument('--analyze-only', metavar='DATA_FILE',
                        help='Skip scraping, analyze an existing data file')
    parser.add_argument('--scraper', metavar='NAME', default='hybrid_scraper',
                        help='Scraper plugin to use (default: hybrid_scraper)')
    parser.add_argument('--track-only', action='store_true',
                        help='Skip scraping and analysis, just update the spreadsheet')
    parser.add_argument('--reset-cache', action='store_true',
                        help='Reset job deduplication cache before scraping')
    parser.add_argument('--reanalyze', action='store_true',
                        help='Re-analyze existing jobs with current scoring logic (no scraping)')
    parser.add_argument('--job-ids', metavar='IDS',
                        help='Comma-separated job IDs to re-analyze (use with --reanalyze)')

    args = parser.parse_args()

    if args.reanalyze:
        if args.scrape_only:
            print("ERROR: Cannot use --reanalyze with --scrape-only")
            sys.exit(1)
        job_ids = None
        if args.job_ids:
            job_ids = [int(x.strip()) for x in args.job_ids.split(',')]
        reanalyze_jobs(args.resume_type, job_ids)
        return

    resume_type = args.resume_type
    resume_path = PROJECT_ROOT / 'resumes' / resume_type / f'{resume_type}.txt'
    search_criteria_path = PROJECT_ROOT / 'resumes' / resume_type / f'{resume_type}_search_criteria.json'

    if not resume_path.exists():
        print(f"Error: Resume not found at {resume_path}")
        print(f"Expected: resumes/{resume_type}/{resume_type}.txt")
        sys.exit(1)

    data_file = args.analyze_only

    # ── Step 1: Scrape ─────────────────────────────────────────────
    if not args.track_only and not data_file:
        print(f"\n{'='*60}")
        print(f"STEP 1: SCRAPING JOBS [{resume_type}]")
        print(f"{'='*60}")

        if not search_criteria_path.exists():
            print(f"Error: Search criteria not found at {search_criteria_path}")
            print(f"Expected: resumes/{resume_type}/{resume_type}_search_criteria.json")
            sys.exit(1)

        sys.path.insert(0, str(PROJECT_ROOT))
        from scrapers.registry import get_scraper

        try:
            ScraperClass = get_scraper(args.scraper)
        except ValueError as e:
            print(f"ERROR: {e}")
            sys.exit(1)

        scraper = ScraperClass(
            search_criteria_path=str(search_criteria_path),
            resume_type=resume_type,
            reset_cache=args.reset_cache
        )
        data_file = scraper.scrape(output_dir=str(PROJECT_ROOT / 'data'))

        if args.scrape_only:
            print(f"\nScrape complete.")
            print(f"Analyze with: python applicationagent.py {resume_type} --analyze-only {data_file}")
            return

    # ── Step 2: Analyze ────────────────────────────────────────────
    if not args.track_only:
        print(f"\n{'='*60}")
        print(f"STEP 2: ANALYZING JOB FIT [{resume_type}]")
        print(f"{'='*60}")

        sys.path.insert(0, str(PROJECT_ROOT))
        from scripts.batch_analyzer import analyze_batch

        analyze_batch(
            jobs_file=data_file,
            resume_path=str(resume_path),
        )

    # ── Step 3: Track ──────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"STEP 3: UPDATING SPREADSHEET")
    print(f"{'='*60}")

    from scripts.tracker import run_tracker
    run_tracker(output_dir=str(PROJECT_ROOT / 'output' / 'excel'))

    print(f"\n{'='*60}")
    print(f"DONE")
    print(f"{'='*60}")
    print(f"  Spreadsheet: output/excel/job_tracker.xlsx")
    print(f"  PDFs:        output/pdf/")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
