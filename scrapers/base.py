"""
ApplicationAgent — Scraper Base Class

All scrapers (built-in and user plugins) must inherit from BaseScraper
and implement the scrape() method.

Output contract:
    scrape() must return the path to a JSON file with this structure:
    {
        "scraped_at": "<ISO timestamp>",
        "source":     "<scraper name>",      # e.g. "hybrid_scraper"
        "resume_type": "<resume type>",
        "total_jobs": <int>,
        "jobs": [
            {
                "id":          "<unique string>",
                "title":       "<job title>",
                "company":     "<company name>",
                "location":    "<location string>",
                "salary":      "<salary string or null>",
                "url":         "<job posting URL>",
                "description": "<full job description text>",
                "scraped_at":  "<ISO timestamp>",
                "search_query": "<query string that found this job>"
            },
            ...
        ]
    }
"""

from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime
import json


class BaseScraper(ABC):
    """
    Abstract base class for ApplicationAgent scrapers.

    Class attributes (required on subclasses):
        name         - machine-readable identifier, used in filenames and DB.
                       Use lowercase with underscores. Must be unique.
        display_name - human-readable name shown in the UI.

    Example:
        class MyScraper(BaseScraper):
            name = "my_scraper"
            display_name = "My Job Board"

            def scrape(self, output_dir):
                jobs = self._fetch_jobs()
                return self.save_results(jobs, output_dir)
    """

    name: str = "base"
    display_name: str = "Base Scraper"

    def __init__(self, search_criteria_path, config_path=None, resume_type='default', reset_cache=False):
        """
        Args:
            search_criteria_path: Path to the resume's *_search_criteria.json
            config_path:          Path to global scraper_config.json (optional)
            resume_type:          Resume identifier — used in output filename
            reset_cache:          If True, clear dedup cache before scraping
        """
        self.resume_type = resume_type
        self.reset_cache = reset_cache
        self.search_criteria_path = search_criteria_path
        self.config_path = config_path

        # Load search criteria
        if search_criteria_path and Path(search_criteria_path).exists():
            with open(search_criteria_path) as f:
                criteria = json.load(f)
            self.search_queries = criteria.get('search_queries', [])
            self.exclude_keywords = criteria.get('exclude_keywords', [])
            self.location_preferences = criteria.get('location_preferences', [])
        else:
            self.search_queries = []
            self.exclude_keywords = []
            self.location_preferences = []

    @abstractmethod
    def scrape(self, output_dir: str) -> str:
        """
        Run the scraper. Must return path to the output JSON file.

        Args:
            output_dir: Directory where the output JSON should be saved.

        Returns:
            Absolute path to the written JSON file.
        """

    def save_results(self, jobs: list, output_dir: str) -> str:
        """
        Helper: write scraped jobs to the standard output JSON format.
        Filename: {scraper_name}_{resume_type}_{YYYY-MM-DD}.json

        Call this from your scrape() implementation.
        """
        output_path = Path(output_dir) / 'scraped'
        output_path.mkdir(parents=True, exist_ok=True)

        date_str = datetime.now().strftime('%Y-%m-%d')
        filename = f"{self.name}_{self.resume_type}_{date_str}.json"
        filepath = output_path / filename

        payload = {
            'scraped_at': datetime.now().isoformat(),
            'source': self.name,
            'resume_type': self.resume_type,
            'total_jobs': len(jobs),
            'jobs': jobs,
        }

        with open(filepath, 'w') as f:
            json.dump(payload, f, indent=2)

        return str(filepath)

    @classmethod
    def info(cls) -> dict:
        """Return scraper metadata for the UI."""
        return {
            'name': cls.name,
            'display_name': cls.display_name,
        }
