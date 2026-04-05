"""
Live API smoke test — makes one real call to the Anthropic API.

Run with:
    pytest tests/integration/test_live_api.py --live-api -v

Skipped automatically in all other pytest runs.
Cost: ~$0.004 per run (one claude-sonnet-4-6 call).

Saves full results to tests/output/live_api_result.json for PDF report rendering.
"""

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.live]

PROJECT_ROOT = Path(__file__).parent.parent.parent
FIXTURES_DIR = Path(__file__).parent.parent / 'fixtures'
RESULT_PATH  = PROJECT_ROOT / 'tests' / 'output' / 'live_api_result.json'

LIVE_JOB = (
    "Senior Site Reliability Engineer — Remote (Portland preferred). "
    "10+ years Kubernetes, Terraform, AWS. Build and operate cloud-native platform. "
    "Prometheus, Grafana, incident response. Senior-level role."
)


@pytest.fixture(autouse=True)
def require_live_api(request):
    if not request.config.getoption('--live-api'):
        pytest.skip('Pass --live-api to run live API smoke tests')
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / '.env')
    if not os.getenv('ANTHROPIC_API_KEY'):
        pytest.fail('ANTHROPIC_API_KEY not set — add it to .env or export it')


@pytest.mark.live
def test_live_analyze_job_fit():
    """
    One real Anthropic API call: analyze a short SRE job against the fixture resume.
    Captures raw HTTP response, usage stats, auth verification, and full analysis.
    Saves to tests/output/live_api_result.json for PDF report.
    """
    import core.agent as agent_module
    from core.agent import analyze_job_fit

    resume_text = (FIXTURES_DIR / 'sample_resume.txt').read_text()
    api_key     = os.getenv('ANTHROPIC_API_KEY', '')
    key_preview = f"{api_key[:12]}...{api_key[-4:]}" if len(api_key) > 16 else '(too short)'

    # ── Spy on the raw Anthropic response ─────────────────────────────────────
    captured = {}
    original_create = agent_module.client.messages.create

    def spy_create(**kwargs):
        captured['request'] = {
            'model':      kwargs.get('model'),
            'max_tokens': kwargs.get('max_tokens'),
            'message_count': len(kwargs.get('messages', [])),
            'prompt_chars':  len(kwargs.get('messages', [{}])[0].get('content', '')),
        }
        response = original_create(**kwargs)
        captured['response_raw'] = {
            'id':           response.id,
            'type':         response.type,
            'model':        response.model,
            'stop_reason':  response.stop_reason,
            'stop_sequence': response.stop_sequence,
            'input_tokens':  response.usage.input_tokens,
            'output_tokens': response.usage.output_tokens,
            'response_chars': len(response.content[0].text) if response.content else 0,
        }
        return response

    # ── Run analysis with spy active ───────────────────────────────────────────
    t0 = time.time()
    with patch.object(agent_module.client.messages, 'create', side_effect=spy_create):
        result = analyze_job_fit(
            job_description=LIVE_JOB,
            resume_text=resume_text,
            resume_type='devops_sre',
            location_preferences=['Portland', 'Remote'],
        )
    elapsed = round(time.time() - t0, 2)

    raw = captured.get('response_raw', {})
    req = captured.get('request', {})

    # ── Cost estimate ──────────────────────────────────────────────────────────
    input_tokens  = raw.get('input_tokens', 0)
    output_tokens = raw.get('output_tokens', 0)
    # claude-sonnet-4-6: $3/M input, $15/M output
    cost_usd = round((input_tokens * 3 + output_tokens * 15) / 1_000_000, 5)

    # ── Console output ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  LIVE API SMOKE TEST — RESULTS")
    print(f"{'='*60}")
    print(f"\n  AUTH")
    print(f"    Key prefix : {key_preview}")
    print(f"    HTTP status: 200 OK (authenticated)")

    print(f"\n  REQUEST")
    print(f"    Model      : {req.get('model')}")
    print(f"    Max tokens : {req.get('max_tokens')}")
    print(f"    Messages   : {req.get('message_count')}")
    print(f"    Prompt size: {req.get('prompt_chars'):,} chars")

    print(f"\n  RESPONSE")
    print(f"    Response ID  : {raw.get('id')}")
    print(f"    Model served : {raw.get('model')}")
    print(f"    Stop reason  : {raw.get('stop_reason')}")
    print(f"    Input tokens : {input_tokens:,}")
    print(f"    Output tokens: {output_tokens:,}")
    print(f"    Response size: {raw.get('response_chars'):,} chars")
    print(f"    Latency      : {elapsed}s")
    print(f"    Est. cost    : ${cost_usd}")

    print(f"\n  ANALYSIS RESULT")
    print(f"    Decision   : {result['decision']}")
    print(f"    Fit score  : {result['fit_score']:.2f}")
    ai = result['ai_analysis']
    print(f"    Should apply     : {ai.get('should_apply')}")
    print(f"    ATS likelihood   : {ai.get('ats_pass_likelihood')}")
    print(f"    Experience level : {ai.get('experience_level')}")
    print(f"    Role fit         : {ai.get('role_fit')}")
    print(f"    Interview warning: {ai.get('interview_warning')}")
    print(f"    Confidence       : {ai.get('confidence', 0):.0%}")
    print(f"\n  KEYWORDS MATCHED ({len(ai.get('keyword_matches', []))})")
    for kw in ai.get('keyword_matches', []):
        print(f"    + {kw}")
    print(f"\n  KEYWORDS MISSING ({len(ai.get('missing_keywords', []))})")
    for kw in ai.get('missing_keywords', []):
        print(f"    - {kw}")
    print(f"\n  STRENGTHS")
    for s in ai.get('competitive_strengths', []):
        print(f"    ✓ {s}")
    print(f"\n  GAPS")
    for g in ai.get('competitive_gaps', []):
        print(f"    ✗ {g}")
    print(f"\n  STRATEGY")
    print(f"    {ai.get('application_strategy', '')}")
    print(f"\n  REASONING")
    print(f"    {ai.get('overall_reasoning', '')}")
    print(f"\n{'='*60}\n")

    # ── Save JSON sidecar for PDF report ───────────────────────────────────────
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps({
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'key_preview': key_preview,
        'auth_status': '200 OK',
        'request': req,
        'response_raw': raw,
        'elapsed_s': elapsed,
        'cost_usd': cost_usd,
        'result': {
            'decision':    result['decision'],
            'fit_score':   result['fit_score'],
            'resume_type': result['resume_type'],
        },
        'ai_analysis': ai,
        'quick_analysis': result['quick_analysis'],
        'job_description': LIVE_JOB,
        'resume_file': str(FIXTURES_DIR / 'sample_resume.txt'),
    }, indent=2))

    # ── Assertions ─────────────────────────────────────────────────────────────
    assert result['decision'] in {'STRONG_MATCH', 'APPLY', 'ATS_ONLY', 'MAYBE', 'SKIP'}
    assert isinstance(result['fit_score'], float)
    assert 0.0 <= result['fit_score'] <= 1.0
    assert isinstance(ai.get('keyword_matches'), list)
    assert isinstance(ai.get('missing_keywords'), list)
    assert ai.get('experience_level') in {'APPROPRIATE', 'OVER_QUALIFIED', 'UNDER_QUALIFIED', 'UNKNOWN'}
    assert ai.get('ats_pass_likelihood') in {'HIGH', 'MEDIUM', 'LOW', 'UNKNOWN'}
    assert ai.get('role_fit') in {'EXCELLENT', 'GOOD', 'FAIR', 'POOR', 'UNKNOWN'}
    assert ai.get('should_apply') in {'DEFINITELY', 'PROBABLY', 'MAYBE', 'NO', 'ERROR'}
    assert 0.0 <= float(ai.get('confidence', 0)) <= 1.0
    assert raw.get('stop_reason') == 'end_turn', f"Unexpected stop reason: {raw.get('stop_reason')}"
    assert result['decision'] != 'SKIP', (
        f"Expected at least MAYBE for a strong SRE match — got SKIP "
        f"(fit_score={result['fit_score']:.2f})"
    )
