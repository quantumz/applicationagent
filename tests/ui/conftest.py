import pytest
import subprocess
import threading
import time
import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).parent.parent.parent
BASE_URL = "http://localhost:8081"  # use 8081 to avoid conflicts with dev server on 8080


def _drain(pipe):
    """Read and discard subprocess output so the pipe never blocks."""
    try:
        for _ in pipe:
            pass
    except Exception:
        pass


@pytest.fixture(scope="session")
def flask_server(tmp_path_factory):
    """Start Flask on port 8081 for the test session."""
    tmp = tmp_path_factory.mktemp("ui_test")
    env = os.environ.copy()
    env['APPLICATIONAGENT_ROOT'] = str(tmp)
    env['FLASK_TEST_PORT'] = '8081'
    # PYTHONPATH must include the real project root so 'core', 'scrapers', etc. are importable
    # even though APPLICATIONAGENT_ROOT points to the tmp data directory.
    existing_pythonpath = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = f"{PROJECT_ROOT}:{existing_pythonpath}" if existing_pythonpath else str(PROJECT_ROOT)

    # Create minimal .env with test API key from environment
    api_key = os.getenv('ANTHROPIC_API_KEY', '')
    (tmp / '.env').write_text(f'ANTHROPIC_API_KEY={api_key}\n')

    # Create required directories
    (tmp / 'data').mkdir()
    (tmp / 'output' / 'pdf').mkdir(parents=True)
    (tmp / 'output' / 'excel').mkdir(parents=True)
    (tmp / 'resumes').mkdir()
    (tmp / 'logs').mkdir()

    proc = subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / 'ui' / 'app.py')],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    # Drain stdout in a background thread so the pipe never fills and blocks Flask
    drain_thread = threading.Thread(target=_drain, args=(proc.stdout,), daemon=True)
    drain_thread.start()

    # Wait up to 10s for Flask to be ready
    import urllib.request
    for _ in range(20):
        try:
            urllib.request.urlopen(f'{BASE_URL}/')
            break
        except Exception:
            time.sleep(0.5)

    yield tmp

    proc.terminate()
    proc.wait()


@pytest.fixture(scope="session")
def browser_context(flask_server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        yield context
        browser.close()


@pytest.fixture
def page(browser_context, flask_server):
    page = browser_context.new_page()
    page.goto(BASE_URL)
    # Seed the API key via API if not already configured — no browser modal interaction needed
    api_key = os.getenv('ANTHROPIC_API_KEY', 'sk-ant-test')
    page.evaluate(f"""async () => {{
        const res = await fetch('/api/settings/status');
        const data = await res.json();
        if (!data.api_key_configured) {{
            await fetch('/api/settings/apikey', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{api_key: '{api_key}'}})
            }});
        }}
    }}""")
    page.reload()
    yield page
    page.close()
