"""
core/resume.py — Resume file loading helpers

Centralizes the repeated patterns across applicationagent.py,
ui/app.py, and scripts/batch_analyzer.py:
  - Read resume text from resumes/<name>/<name>.txt
  - Read location_preferences from resumes/<name>/<name>_search_criteria.json
"""

import json
from pathlib import Path


def load_resume(resume_type: str, project_root: Path) -> str:
    """Read resume plain text from the standard filesystem location.

    Args:
        resume_type: Resume folder/file stem (e.g. 'sre').
        project_root: Absolute path to the project root directory.

    Returns:
        Resume text as a string.

    Raises:
        FileNotFoundError: If resumes/<resume_type>/<resume_type>.txt does not exist.
    """
    path = project_root / 'resumes' / resume_type / f'{resume_type}.txt'
    if not path.exists():
        raise FileNotFoundError(f'Resume not found: {path}')
    return path.read_text()


def load_location_preferences(resume_type: str, project_root: Path) -> list | None:
    """Read location_preferences from the resume's search_criteria.json.

    Args:
        resume_type: Resume folder/file stem (e.g. 'sre').
        project_root: Absolute path to the project root directory.

    Returns:
        List of location preference strings, or None if the criteria file
        does not exist or contains no location_preferences key.
    """
    criteria_path = project_root / 'resumes' / resume_type / f'{resume_type}_search_criteria.json'
    if not criteria_path.exists():
        return None
    criteria = json.loads(criteria_path.read_text())
    return criteria.get('location_preferences')
