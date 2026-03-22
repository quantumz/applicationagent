"""
ApplicationAgent — Scraper Registry

Discovers and loads scraper plugins from two locations:
  1. scrapers/          — built-in scrapers (shipped with the project)
  2. scrapers/plugins/  — user-added scrapers (not tracked by git)

Any .py file in either directory that contains a class inheriting from
BaseScraper is automatically registered. No configuration required.

Usage:
    from scrapers.registry import get_scrapers, get_scraper

    # All available scrapers (for UI dropdown)
    scrapers = get_scrapers()
    # [{'name': 'hybrid_scraper', 'display_name': 'Hybrid Scraper'}, ...]

    # Instantiate one by name
    cls = get_scraper('hybrid_scraper')
    instance = cls(search_criteria_path=..., resume_type=...)
"""

import importlib.util
import inspect
import sys
from pathlib import Path

from scrapers.base import BaseScraper

# Paths are resolved relative to this file, not the working directory.
# Safe to invoke from any working directory (e.g. pytest from project root or tests/).
_SCRAPERS_DIR = Path(__file__).parent
_PLUGINS_DIR  = _SCRAPERS_DIR / 'plugins'

# Internal cache: name -> class
_registry: dict[str, type[BaseScraper]] = {}


def _load_module_from_path(path: Path):
    """Import a .py file as a module without adding it to sys.modules permanently."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        print(f"  [registry] Could not load {path.name}: {e}")
        return None
    return module


def _discover(directory: Path):
    """Scan a directory for BaseScraper subclasses and register them."""
    if not directory.exists():
        return
    for path in sorted(directory.glob('*.py')):
        if path.name.startswith('_'):
            continue  # skip __init__.py, base.py, registry.py
        module = _load_module_from_path(path)
        if module is None:
            continue
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BaseScraper)
                and obj is not BaseScraper
                and hasattr(obj, 'name')
                and obj.name != 'base'
            ):
                _registry[obj.name] = obj


def _ensure_loaded():
    if _registry:
        return
    _discover(_SCRAPERS_DIR)
    _discover(_PLUGINS_DIR)


def get_scrapers() -> list[dict]:
    """Return metadata for all registered scrapers, sorted by display_name."""
    _ensure_loaded()
    return sorted(
        [cls.info() for cls in _registry.values()],
        key=lambda s: s['display_name']
    )


def get_scraper(name: str) -> type[BaseScraper]:
    """
    Return the scraper class for the given name.
    Raises ValueError if not found.
    """
    _ensure_loaded()
    if name not in _registry:
        available = ', '.join(_registry.keys()) or 'none'
        raise ValueError(f"Unknown scraper '{name}'. Available: {available}")
    return _registry[name]
