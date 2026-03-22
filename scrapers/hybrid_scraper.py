"""
Hybrid Scraper - Human in the Loop
YOU solve the Cloudflare challenge, then automation takes over
"""

import json
import os
import time
import random
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import sys

PROJECT_ROOT = Path(__file__).parent.parent

from scrapers.base import BaseScraper


class HybridScraper(BaseScraper):
    name = "hybrid_scraper"
    display_name = "Hybrid Scraper"
    def __init__(self, search_criteria_path=None, config_path=None, resume_type='default', reset_cache=False):
        """Initialize hybrid scraper

        Args:
            config_path: Path to scraper_config.json (rate limits, browser settings)
            search_criteria_path: Path to resume-specific search criteria JSON
            resume_type: Resume type identifier, used in output filename
            reset_cache: If True, clear jobs_seen.txt before scraping
        """
        config_path = config_path or PROJECT_ROOT / 'scrapers' / 'scraper_config.json'

        with open(config_path, 'r') as f:
            self.config = json.load(f)

        self.rate_limit = self.config['rate_limiting']
        self.browser_config = self.config['browser_config']
        self.resume_type = resume_type

        # Load search criteria (queries + resume-specific excludes)
        if search_criteria_path:
            with open(search_criteria_path, 'r') as f:
                criteria = json.load(f)
            self.search_queries = criteria.get('search_queries', [])
            # Merge global hard-exclusions with resume-specific excludes
            global_excludes = self.config.get('exclude_keywords', [])
            resume_excludes = criteria.get('exclude_keywords', [])
            self.exclude_keywords = list(set(global_excludes + resume_excludes))
        else:
            self.search_queries = self.config.get('search_queries', [])
            self.exclude_keywords = self.config.get('exclude_keywords', [])

        self.jobs_scraped = []

        # jobs_seen.txt lives in scrapers/ — path is always relative to this file
        self.seen_file = Path(__file__).parent / 'jobs_seen.txt'
        if reset_cache and self.seen_file.exists():
            print("🔄 Resetting job cache...")
            self.seen_file.unlink()

        if self.seen_file.exists():
            with open(self.seen_file, 'r') as f:
                self.urls_seen = set(line.strip() for line in f if line.strip())
            print(f"📋 Loaded {len(self.urls_seen)} previously seen jobs")
        else:
            self.urls_seen = set()
            print("📋 Starting fresh - no job cache found")

    def human_delay(self, min_sec=None, max_sec=None):
        """Random delay to simulate human behavior"""
        min_sec = min_sec or self.rate_limit['min_delay_seconds']
        max_sec = max_sec or self.rate_limit['max_delay_seconds']
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)

    def wait_for_human(self, page):
        """Wait for human to solve Cloudflare challenge"""
        print("\n" + "="*60)
        print("⚠️  CLOUDFLARE DETECTED")
        print("="*60)
        print("Please solve the Cloudflare challenge in the browser window.")
        print("Once you see job listings, the scraper will continue automatically.")
        print("\nWaiting for you to solve the challenge...")
        print("(Watching for job cards to appear...)")
        print("="*60 + "\n")

        max_wait = 120  # 2 minutes max
        start_time = time.time()

        while time.time() - start_time < max_wait:
            try:
                if page.query_selector('article.job_result') or \
                   page.query_selector('[data-testid="job-card"]') or \
                   page.query_selector('.jobsearch-JobInfoHeader-title'):
                    print("✓ Challenge solved! Continuing with automation...\n")
                    return True

                content = page.content().lower()
                if 'cloudflare' in content and 'verify' in content:
                    time.sleep(2)
                    continue

                if 'jobs' in page.url.lower() or 'search' in page.url.lower():
                    print("✓ Page loaded, proceeding...\n")
                    return True

            except:
                time.sleep(2)
                continue

        print("❌ Timeout waiting for challenge to be solved")
        return False

    def should_exclude_job(self, title, description):
        """Check if job should be excluded based on keywords"""
        import re

        title_lower = title.lower()
        desc_lower = description.lower()

        for keyword in self.exclude_keywords:
            keyword_lower = keyword.lower()

            # Seniority keywords: check title only to avoid false positives
            if keyword_lower in ['intern', 'junior', 'entry level', 'student', 'test engineer', 'qa', 'quality assurance', 'qa engineer']:
                pattern = r'\b' + re.escape(keyword_lower) + r'\b'
                if re.search(pattern, title_lower):
                    return True, keyword

            # Other keywords: check title and description
            else:
                combined = f"{title_lower} {desc_lower}"
                if keyword_lower in combined:
                    return True, keyword

        return False, None

    def build_search_url(self, keywords, location):
        """Build ZipRecruiter search URL"""
        search = keywords.replace(' ', '+')
        loc = location.replace(' ', '+').replace(',', '%2C')
        base_url = "https://www.ziprecruiter.com/jobs-search"
        return f"{base_url}?search={search}&location={loc}"

    def extract_job_data(self, page, job_card):
        """Extract data from a job card"""
        try:
            job_card.click()
            self.human_delay(3, 5)

            try:
                page.wait_for_load_state('networkidle', timeout=5000)
            except:
                pass

            time.sleep(2)

            # Find detail panel
            detail_panel = None
            try:
                detail_panel = page.query_selector('[data-testid="job-details-scroll-container"]')
                if not detail_panel:
                    detail_panel = page.query_selector('[class*="job-details"]')
                if not detail_panel:
                    detail_panel = page.query_selector('[class*="details-scroll"]')
                if not detail_panel:
                    detail_panel = page.query_selector('[class*="right"]')
            except:
                pass

            search_context = detail_panel if detail_panel else page

            # Title
            try:
                h2_elements = search_context.query_selector_all('h2')
                if h2_elements:
                    title = ' '.join(h2_elements[0].inner_text().split())
                else:
                    heading = search_context.query_selector('h1, h2, h3')
                    title = ' '.join(heading.inner_text().split()) if heading else "Unknown Title"
            except Exception as e:
                print(f"    ⚠️  Error extracting title: {e}")
                title = "Unknown Title"

            # Company
            try:
                links = search_context.query_selector_all('a')
                company = "Unknown Company"
                for link in links[:15]:
                    text = link.inner_text().strip()
                    if text and text not in ['Job Postings', 'Log In', 'Jobs', 'Quick apply', 'Apply', 'New']:
                        if len(text) > 2 and len(text) < 100 and text[0].isupper():
                            if not any(state in text for state in [', OR', ', WA', ', CA', ', NY', 'Remote']):
                                company = ' '.join(text.split())
                                break
            except Exception as e:
                print(f"    ⚠️  Error extracting company: {e}")
                company = "Unknown Company"

            # Location
            try:
                all_elements = search_context.query_selector_all('div, span, p, a')
                location = "Unknown Location"
                loc_patterns = [
                    ', al', ', ak', ', az', ', ar', ', ca', ', co', ', ct', ', de', ', fl',
                    ', ga', ', hi', ', id', ', il', ', in', ', ia', ', ks', ', ky', ', la',
                    ', me', ', md', ', ma', ', mi', ', mn', ', ms', ', mo', ', mt', ', ne',
                    ', nv', ', nh', ', nj', ', nm', ', ny', ', nc', ', nd', ', oh', ', ok',
                    ', or', ', pa', ', ri', ', sc', ', sd', ', tn', ', tx', ', ut', ', vt',
                    ', va', ', wa', ', wv', ', wi', ', wy', ', dc',
                    'remote', 'hybrid', 'on-site', 'onsite',
                ]
                for elem in all_elements[:40]:
                    text = elem.inner_text().strip()
                    if text and len(text) < 120 and text != title:
                        if any(p in text.lower() for p in loc_patterns):
                            location = ' '.join(text.split('•')[0].split())
                            break
            except Exception as e:
                print(f"    ⚠️  Error extracting location: {e}")
                location = "Unknown Location"

            # Salary
            try:
                salary = None
                all_text = search_context.query_selector_all('div, span, p')
                for elem in all_text[:40]:
                    text = elem.inner_text().strip()
                    if '$' in text and any(char.isdigit() for char in text) and len(text) < 100:
                        salary = ' '.join(text.split())
                        break
            except:
                salary = None

            # Description
            try:
                desc_elem = search_context.query_selector('[class*="description"]')
                if not desc_elem:
                    desc_elem = search_context.query_selector('[class*="whitespace"]')
                if not desc_elem:
                    desc_elem = search_context
                description = desc_elem.inner_text().strip() if desc_elem else ""
            except:
                description = ""

            url = page.url
            job_id = url.split('/')[-1].split('?')[0] if '/' in url else None

            print(f"    Extracted: {title[:50]}... at {company}")

            if title == "Unknown Title" and company == "Unknown Company":
                print(f"    ⚠️  Extraction failed completely")
                return None

            return {
                'id': job_id,
                'url': url,
                'title': title,
                'company': company,
                'location': location,
                'salary': salary,
                'description': description,
                'scraped_at': datetime.now().isoformat()
            }

        except Exception as e:
            print(f"  ⚠️  Error extracting job data: {e}")
            return None

    def scrape_search_results(self, page, keywords, location, max_results):
        """Scrape jobs from a single search results page"""
        url = self.build_search_url(keywords, location)

        print(f"\n{'='*60}")
        print(f"🤝 HYBRID MODE: Searching {keywords} in {location}")
        print(f"URL: {url}")
        print(f"Max results: {max_results}")
        print(f"{'='*60}")

        try:
            page.goto(url, wait_until='load', timeout=30000)
            print("  ✓ Page loaded")
            self.human_delay(2, 4)

            content = page.content().lower()
            if 'cloudflare' in content and 'verify' in content:
                if not self.wait_for_human(page):
                    print("  ❌ Could not proceed - Cloudflare not solved")
                    return []

            try:
                page.keyboard.press('Escape')
                self.human_delay(1, 2)
            except:
                pass

            try:
                page.wait_for_selector('.job_result_two_pane_v2', timeout=10000)
                print("  ✓ Job cards loaded")
            except PlaywrightTimeout:
                try:
                    page.wait_for_selector('article[id*="job_"]', timeout=10000)
                    print("  ✓ Job cards loaded (article selector)")
                except PlaywrightTimeout:
                    print("  ❌ No jobs found")
                    return []

            for _ in range(3):
                page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                self.human_delay(1, 2)

            job_cards = page.query_selector_all('.job_result_two_pane_v2')
            if not job_cards:
                job_cards = page.query_selector_all('article[id*="job_"]')

            print(f"  ✓ Found {len(job_cards)} job cards")

            jobs_from_search = []

            for i, card in enumerate(job_cards):
                if i >= max_results:
                    print(f"  Reached max results ({max_results})")
                    break

                if len(self.jobs_scraped) >= self.rate_limit['max_jobs_per_run']:
                    print(f"  Reached global max ({self.rate_limit['max_jobs_per_run']})")
                    break

                print(f"\n  Processing job {i+1}/{min(max_results, len(job_cards))}...")

                job_data = self.extract_job_data(page, card)

                if not job_data:
                    continue

                if job_data['url'] in self.urls_seen:
                    print(f"    ⏭️  Duplicate")
                    continue

                excluded, keyword = self.should_exclude_job(job_data['title'], job_data['description'])
                if excluded:
                    print(f"    ⏭️  Excluded ('{keyword}')")
                    continue

                print(f"    ✓ {job_data['title']} at {job_data['company']}")
                jobs_from_search.append(job_data)
                self.jobs_scraped.append(job_data)
                self.urls_seen.add(job_data['url'])

                self.human_delay()

            return jobs_from_search

        except Exception as e:
            print(f"  ❌ Error during search: {e}")
            return []

    def scrape(self, output_dir=None):
        """Main scraping function with human assistance"""
        output_dir = output_dir or str(PROJECT_ROOT / 'data')

        print("="*60)
        print("🤝 HYBRID SCRAPER - Human + Automation")
        print("="*60)
        print(f"Resume type: {self.resume_type}")
        print(f"Queries: {len(self.search_queries)}")
        print(f"Max jobs per run: {self.rate_limit['max_jobs_per_run']}")
        print(f"Mode: You solve Cloudflare, automation scrapes jobs")
        print("="*60)

        if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
            print("ERROR: Scraping requires a desktop environment.")
            print("The hybrid scraper opens a visible browser for Cloudflare bypass.")
            print("Run this from a desktop session, not a headless or SSH environment.")
            sys.exit(1)

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,  # Must be visible for human interaction
                args=['--disable-blink-features=AutomationControlled']
            )

            context = browser.new_context(
                user_agent=self.browser_config['user_agent'],
                viewport=self.browser_config['viewport'],
            )

            page = context.new_page()

            for query in self.search_queries:
                if len(self.jobs_scraped) >= self.rate_limit['max_jobs_per_run']:
                    print("\nReached global job limit")
                    break

                jobs = self.scrape_search_results(
                    page,
                    query['keywords'],
                    query['location'],
                    min(query['max_results'], self.rate_limit['max_jobs_per_query'])
                )

                print(f"\n✓ Collected {len(jobs)} jobs from this search")
                search_query_str = f"{query['keywords']} {query['location']}"
                for job in jobs:
                    job['search_query'] = search_query_str

                if len(self.search_queries) > 1:
                    print("\nWaiting before next search...")
                    self.human_delay(5, 10)

            print("\n" + "="*60)
            print("Scraping complete.")
            print("="*60)

            browser.close()

        output_file = self.save_results(output_dir)

        if self.jobs_scraped:
            with open(self.seen_file, 'a') as f:
                for job in self.jobs_scraped:
                    f.write(f"{job['url']}\n")
            print(f"💾 Saved {len(self.jobs_scraped)} new URLs to {self.seen_file}")

        print(f"\n{'='*60}")
        print(f"SCRAPING COMPLETE")
        print(f"{'='*60}")
        print(f"New jobs scraped: {len(self.jobs_scraped)}")
        print(f"Total jobs seen (ever): {len(self.urls_seen)}")
        print(f"Saved to: {output_file}")
        print(f"{'='*60}\n")

        return output_file

    def save_results(self, output_dir):
        """Save scraped jobs to JSON — filename: {scraper_name}_{resume_type}_{date}.json"""
        output_path = Path(output_dir) / 'scraped'
        output_path.mkdir(parents=True, exist_ok=True)

        date_str = datetime.now().strftime('%Y-%m-%d')
        filename = f"{self.name}_{self.resume_type}_{date_str}.json"
        filepath = output_path / filename

        output_data = {
            'scraped_at': datetime.now().isoformat(),
            'source': self.name,
            'method': 'hybrid_human_automation',
            'resume_type': self.resume_type,
            'total_jobs': len(self.jobs_scraped),
            'queries': self.search_queries,
            'jobs': self.jobs_scraped
        }

        with open(filepath, 'w') as f:
            json.dump(output_data, f, indent=2)

        return str(filepath)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Hybrid job scraper with deduplication')
    parser.add_argument('resume_type', nargs='?', default=None,
                        help='Resume type to use (must match a folder in resumes/)')
    parser.add_argument('--config', default=None,
                        help='Path to scraper_config.json (default: scrapers/scraper_config.json)')
    parser.add_argument('--reset', action='store_true',
                        help='Reset job cache (re-scrape all jobs)')

    args = parser.parse_args()

    search_criteria = PROJECT_ROOT / 'resumes' / args.resume_type / f'{args.resume_type}_search_criteria.json'
    if not search_criteria.exists():
        print(f"Error: Search criteria not found at {search_criteria}")
        sys.exit(1)

    scraper = HybridScraper(
        config_path=args.config,
        search_criteria_path=str(search_criteria),
        resume_type=args.resume_type,
        reset_cache=args.reset
    )
    output_file = scraper.scrape()

    print(f"\nNext step: Analyze these jobs")
    print(f"  python applicationagent.py {args.resume_type} --analyze-only {output_file}\n")


if __name__ == "__main__":
    main()
