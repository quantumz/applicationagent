"""
ApplicationAgent Web UI
Flask-based local interface — terminal aesthetic, no framework
"""

from flask import Flask, render_template, request, jsonify, Response, send_file, abort
from pathlib import Path
from datetime import datetime
import base64
import json
import os
import re
import subprocess
import sys
from dotenv import load_dotenv

import logging

_log_level = logging.DEBUG if os.environ.get('APPLICATIONAGENT_DEBUG') else logging.WARNING
logging.basicConfig(
    level=_log_level,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
_root_override = os.environ.get('APPLICATIONAGENT_ROOT')
if _root_override:
    PROJECT_ROOT = Path(_root_override).resolve()
else:
    PROJECT_ROOT = Path(__file__).parent.parent.resolve()
ENV_PATH = PROJECT_ROOT / '.env'
load_dotenv(ENV_PATH, override=True)  # load at startup so key is in os.environ

# Init DB and migrate existing JSON data on startup
sys.path.insert(0, str(PROJECT_ROOT))
from core.database import init_db, import_from_json, migrate_resumes_from_fs

def _startup():
    init_db()
    imported = import_from_json(PROJECT_ROOT / 'data')
    if imported:
        print(f'[DB] Imported {imported} jobs from existing JSON files')
    resumes = migrate_resumes_from_fs(PROJECT_ROOT)
    if resumes:
        print(f'[DB] Registered {resumes} resume(s) from filesystem')

_startup()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/resumes')
def get_resumes():
    from core.database import get_resumes_list, get_resume_stats, migrate_resumes_from_fs
    # Sync any new resume folders added since startup
    migrate_resumes_from_fs(PROJECT_ROOT)
    resumes = get_resumes_list()
    result = []
    for r in resumes:
        fp = Path(r['file_path'])
        word_count = 0
        last_updated = ''
        if fp.exists():
            try:
                word_count = len(fp.read_text().split())
                import datetime as _dt
                last_updated = _dt.datetime.fromtimestamp(fp.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
            except Exception:
                pass
        stats = get_resume_stats(r['id'])
        result.append({
            'id': r['id'],
            'name': r['name'],
            'file_path': r['file_path'],
            'word_count': word_count,
            'last_updated': last_updated,
            'stats': stats,
        })
    return jsonify({'resumes': result})


@app.route('/api/resumes/<int:resume_id>')
def get_resume_detail(resume_id):
    from core.database import get_resume_by_id, get_resume_stats
    resume = get_resume_by_id(resume_id)
    if not resume:
        abort(404)
    fp = Path(resume['file_path'])
    word_count = 0
    last_updated = ''
    if fp.exists():
        try:
            word_count = len(fp.read_text().split())
            import datetime as _dt
            last_updated = _dt.datetime.fromtimestamp(fp.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
        except Exception:
            pass
    resume['word_count'] = word_count
    resume['last_updated'] = last_updated
    resume['stats'] = get_resume_stats(resume_id)
    return jsonify(resume)


@app.route('/api/resumes/<int:resume_id>/queries')
def get_resume_queries_route(resume_id):
    from core.database import get_resume_queries
    return jsonify({'resume_id': resume_id, 'queries': get_resume_queries(resume_id)})


@app.route('/api/resumes/<int:resume_id>', methods=['PUT'])
def update_resume(resume_id):
    from core.database import get_resume_by_id, update_resume_criteria
    data = request.json or {}
    criteria = data.get('search_criteria')
    if criteria is None:
        return jsonify({'error': 'search_criteria required'}), 400
    resume = get_resume_by_id(resume_id)
    if not resume:
        abort(404)
    if not update_resume_criteria(resume_id, criteria):
        abort(404)
    # Write back to filesystem so the scraper picks up changes
    criteria_path = PROJECT_ROOT / 'resumes' / resume['name'] / f'{resume["name"]}_search_criteria.json'
    try:
        with open(criteria_path, 'w') as f:
            json.dump(criteria, f, indent=2)
    except Exception as e:
        return jsonify({'error': f'DB updated but file write failed: {e}'}), 500
    return jsonify({'status': 'ok'})


@app.route('/api/resumes/<int:resume_id>', methods=['DELETE'])
def delete_resume(resume_id):
    import shutil
    from core.database import get_resume_by_id, delete_resume_record
    if request.args.get('confirm') != 'true':
        return jsonify({'error': 'Pass ?confirm=true to confirm deletion'}), 400
    resume = get_resume_by_id(resume_id)
    if not resume:
        abort(404)
    jobs_deleted = delete_resume_record(resume_id)
    resume_dir = PROJECT_ROOT / 'resumes' / resume['name']
    if resume_dir.exists():
        shutil.rmtree(resume_dir)
    return jsonify({'deleted': True, 'jobs_deleted': jobs_deleted, 'name': resume['name']})


@app.route('/api/resumes/<int:resume_id>/upload', methods=['POST'])
def upload_resume_version(resume_id):
    from core.database import get_resume_by_id, upsert_resume
    resume = get_resume_by_id(resume_id)
    if not resume:
        abort(404)

    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    filename = data.get('filename', '').lower()
    if not (filename.endswith('.txt') or filename.endswith('.pdf')):
        return jsonify({'error': 'File must be .txt or .pdf'}), 400

    file_data = data.get('file_data', '')
    if not file_data:
        return jsonify({'error': 'File required'}), 400

    try:
        file_bytes = base64.b64decode(file_data)
    except Exception:
        return jsonify({'error': 'Invalid file data'}), 400

    if len(file_bytes) > 10 * 1024 * 1024:
        return jsonify({'error': 'File too large (10MB max)'}), 413

    resume_dir = PROJECT_ROOT / 'resumes' / resume['name']
    resume_dir.mkdir(parents=True, exist_ok=True)
    txt_path = resume_dir / f'{resume["name"]}.txt'

    if filename.endswith('.pdf'):
        try:
            import fitz
            doc = fitz.open(stream=file_bytes, filetype='pdf')
            text = '\n'.join(page.get_text() for page in doc)
            txt_path.write_text(text, encoding='utf-8')
        except Exception as e:
            return jsonify({'error': f'PDF extraction failed: {e}'}), 500
    else:
        txt_path.write_bytes(file_bytes)

    upsert_resume(resume['name'], str(txt_path), resume['search_criteria'])
    return jsonify({'status': 'ok'})


@app.route('/api/results')
def api_results():
    from core.database import get_results
    resume_type = request.args.get('resume_type', '').strip() or None
    results = get_results(resume_type)
    return jsonify({'results': results, 'count': len(results)})


@app.route('/api/scrapers')
def get_scrapers():
    """Return list of available scraper plugins."""
    try:
        from scrapers.registry import get_scrapers as _get_scrapers
        return jsonify({'scrapers': _get_scrapers()})
    except Exception as e:
        return jsonify({'scrapers': [{'name': 'hybrid_scraper', 'display_name': 'Hybrid Scraper'}],
                        'error': str(e)})


@app.route('/api/data-files')
def get_data_files():
    """List raw scraper output files for Analyze Only mode."""
    resume_type = request.args.get('resume_type', '').strip()
    data_dir = PROJECT_ROOT / 'data' / 'scraped'
    if not data_dir.exists():
        return jsonify({'files': []})
    files = sorted(data_dir.glob('*.json'),
                   key=lambda f: f.stat().st_mtime, reverse=True)
    if resume_type:
        files = [f for f in files if f'_{resume_type}_' in f.name]
    return jsonify({'files': [f.name for f in files]})


@app.route('/api/applied/<int:job_id>', methods=['POST', 'DELETE'])
def toggle_applied(job_id):
    from core.database import set_applied
    set_applied(job_id, request.method == 'POST')
    return jsonify({'status': 'ok'})


@app.route('/api/consider/<int:job_id>', methods=['POST'])
def set_consider_route(job_id):
    from core.database import set_consider
    data = request.json or {}
    current_score = data.get('fit_score', 0.0)
    set_consider(job_id, current_score)
    return jsonify({'status': 'ok', 'decision': 'CONSIDER'})


@app.route('/api/delete-job', methods=['POST'])
def api_delete_job():
    from core.database import delete_job
    data = request.json or {}
    job_id = data.get('id')
    if not job_id:
        return jsonify({'error': 'id required'}), 400

    delete_job(job_id)

    # Clean up PDF
    def clean(s):
        return ''.join(c if c.isalnum() or c in (' ', '-') else '_'
                       for c in (s or '')).replace(' ', '_')
    pdf_name = f"{clean(data.get('company',''))}_{clean(data.get('title',''))}.pdf"[:100]
    pdf_path = PROJECT_ROOT / 'output' / 'pdf' / pdf_name
    pdf_deleted = pdf_path.exists()
    if pdf_deleted:
        pdf_path.unlink()

    return jsonify({'status': 'ok', 'pdf_deleted': pdf_deleted})


@app.route('/api/analyze-single', methods=['POST'])
def analyze_single():
    from core.database import upsert_job, upsert_analysis
    data = request.json or {}
    resume_type = data.get('resume_type', '').strip()
    job_name = data.get('job_name', 'Manual Job').strip()
    company = data.get('company', 'Unknown').strip() or 'Unknown'
    salary = data.get('salary', '').strip()
    job_url = data.get('url', '').strip()
    job_description = data.get('job_description', '').strip()

    if not resume_type or not job_description:
        return jsonify({'error': 'resume_type and job_description required'}), 400

    from core.resume import load_resume, load_location_preferences
    try:
        resume = load_resume(resume_type, PROJECT_ROOT)
    except FileNotFoundError:
        return jsonify({'error': f'Resume not found: resumes/{resume_type}/{resume_type}.txt'}), 400
    location_preferences = load_location_preferences(resume_type, PROJECT_ROOT)

    from core.agent import analyze_job_fit
    now = datetime.now().isoformat()
    result = analyze_job_fit(job_description, resume, resume_type,
                             location_preferences=location_preferences)

    job_id = upsert_job(
        resume_type=resume_type, source='manual',
        title=job_name, company=company,
        location='', salary=salary or None,
        url=job_url, description=job_description, scraped_at=now,
    )
    if job_id:
        upsert_analysis(
            job_id=job_id,
            decision=result['decision'],
            fit_score=result['fit_score'],
            quick_checks=result.get('quick_analysis', {}),
            ai_analysis=result.get('ai_analysis', {}),
        )
        result['id'] = job_id

    result['applied'] = False
    result['job_metadata'] = {
        'title': job_name, 'company': company,
        'location': '', 'salary': salary or None,
        'url': job_url, 'scraped_at': now,
    }

    try:
        from scripts.batch_analyzer import generate_pdf_report
        generate_pdf_report(result, output_dir=str(PROJECT_ROOT / 'output' / 'pdf'))
    except Exception:
        pass

    try:
        from scripts.tracker import run_tracker
        run_tracker(output_dir=str(PROJECT_ROOT / 'output' / 'excel'))
    except Exception:
        pass

    return jsonify(result)


@app.route('/api/upload-resume', methods=['POST'])
def upload_resume():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Resume name required'}), 400
    if not re.match(r'^[a-zA-Z0-9_]+$', name):
        return jsonify({'error': 'Name must be letters, numbers, and underscores only'}), 400

    filename = data.get('filename', '').lower()
    if not (filename.endswith('.txt') or filename.endswith('.pdf')):
        return jsonify({'error': 'File must be .txt or .pdf'}), 400

    file_data = data.get('file_data', '')
    if not file_data:
        return jsonify({'error': 'Resume file required'}), 400

    search_queries = data.get('search_queries', [])
    if not search_queries:
        return jsonify({'error': 'At least one search query required'}), 400

    keywords_raw = data.get('keywords', [])
    exclude_keywords = [k['text'] for k in keywords_raw
                        if k.get('type') == 'exclude' and k.get('text')]
    include_keywords = [k['text'] for k in keywords_raw
                        if k.get('type') == 'include' and k.get('text')]

    try:
        file_bytes = base64.b64decode(file_data)
    except Exception:
        return jsonify({'error': 'Invalid file data'}), 400

    if len(file_bytes) > 10 * 1024 * 1024:
        return jsonify({'error': 'File too large (10MB max)'}), 413

    resume_dir = PROJECT_ROOT / 'resumes' / name
    resume_dir.mkdir(parents=True, exist_ok=True)

    if filename.endswith('.pdf'):
        try:
            import fitz
            doc = fitz.open(stream=file_bytes, filetype='pdf')
            text = '\n'.join(page.get_text() for page in doc)
            (resume_dir / f'{name}.txt').write_text(text, encoding='utf-8')
        except Exception as e:
            return jsonify({'error': f'PDF extraction failed: {e}'}), 500
    else:
        (resume_dir / f'{name}.txt').write_bytes(file_bytes)

    criteria = {'search_queries': search_queries}
    if exclude_keywords:
        criteria['exclude_keywords'] = exclude_keywords
    if include_keywords:
        criteria['include_keywords'] = include_keywords
    with open(resume_dir / f'{name}_search_criteria.json', 'w') as f:
        json.dump(criteria, f, indent=2)

    from core.database import upsert_resume
    resume_id = upsert_resume(name, str(resume_dir / f'{name}.txt'), criteria)
    return jsonify({'name': name, 'id': resume_id, 'status': 'ok'})


SCREENSHOT_EXTRACTION_PROMPT = """
Extract job posting details from this screenshot.

Return ONLY a JSON object with these fields:
{
  "company":    "<company name, or null if not visible>",
  "title":      "<job title, or null if not visible>",
  "salary":     "<salary range as shown, or null if not visible>",
  "url":        "<full job posting URL if visible in address bar or page, or null>",
  "confidence": <0.0 to 1.0 — your confidence in the extraction overall>
}

Rules:
- Return the values exactly as shown in the screenshot — do not reformat or normalize
- If a field is not clearly visible, return null for that field
- For salary: include the full string as shown (e.g. "$150,000 - $180,000/yr" not "$150k")
- For URL: only include if you can see a complete, valid URL — do not guess
- Return ONLY the JSON object, no explanation, no markdown
"""


@app.route('/api/extract-job-screenshot', methods=['POST'])
def extract_job_screenshot():
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400

    image_file = request.files['image']
    allowed = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}
    if image_file.mimetype not in allowed:
        return jsonify({'error': 'Unsupported image type'}), 400

    image_data = image_file.read()
    if len(image_data) > 10 * 1024 * 1024:
        return jsonify({'error': 'Image too large (10MB max)'}), 413

    from anthropic import Anthropic
    client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

    b64 = base64.standard_b64encode(image_data).decode('utf-8')

    try:
        response = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=500,
            messages=[{
                'role': 'user',
                'content': [
                    {
                        'type': 'image',
                        'source': {
                            'type': 'base64',
                            'media_type': image_file.mimetype,
                            'data': b64,
                        }
                    },
                    {
                        'type': 'text',
                        'text': SCREENSHOT_EXTRACTION_PROMPT,
                    }
                ]
            }]
        )
    except Exception as e:
        app.logger.error(f'Vision API error: {e}')
        return jsonify({'error': 'Extraction failed — fill fields manually'}), 500

    raw = response.content[0].text.strip()
    clean = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw, flags=re.MULTILINE).strip()
    try:
        result = json.loads(clean)
    except json.JSONDecodeError:
        return jsonify({'error': 'Could not parse extraction result'}), 500

    return jsonify(result)


# TODO: auth gate before network deployment
@app.route('/api/settings/status')
def settings_status():
    from core.keystore import is_key_configured
    in_memory = bool(os.environ.get('ANTHROPIC_API_KEY', ''))
    in_db = is_key_configured()
    return jsonify({
        'api_key_configured': in_memory,
        'requires_reentry': in_db and not in_memory,
    })


# TODO: auth gate before network deployment
@app.route('/api/settings/apikey', methods=['POST'])
def settings_save_apikey():
    from core.keystore import set_key, mask_key
    data = request.get_json()
    api_key = (data or {}).get('api_key', '').strip()

    if not api_key:
        return jsonify({'error': 'API key required'}), 400
    if not api_key.startswith('sk-ant-'):
        return jsonify({'error': 'Invalid API key format'}), 400

    set_key(api_key)  # hashes to DB, sets os.environ
    app.logger.info('[keystore] API key saved: %s', mask_key(api_key))
    return jsonify({'status': 'ok'})


@app.route('/output/pdf/<path:filename>')
def serve_pdf(filename):
    pdf_path = PROJECT_ROOT / 'output' / 'pdf' / filename
    if not pdf_path.exists() or pdf_path.suffix != '.pdf':
        abort(404)
    return send_file(pdf_path, mimetype='application/pdf')


@app.route('/api/run')
def run_pipeline():
    resume_type = request.args.get('resume_type', '')
    mode = request.args.get('mode', 'full')
    data_file = request.args.get('data_file', '')
    reset_cache = request.args.get('reset_cache', 'false').lower() == 'true'
    scraper = request.args.get('scraper', 'hybrid_scraper').strip() or 'hybrid_scraper'

    if not resume_type:
        return jsonify({'error': 'resume_type required'}), 400

    resume_path = PROJECT_ROOT / 'resumes' / resume_type / f'{resume_type}.txt'
    if not resume_path.exists():
        return jsonify({'error': f'Resume not found'}), 400

    def generate():
        cmd = [sys.executable, str(PROJECT_ROOT / 'applicationagent.py'), resume_type]
        if mode == 'scrape':
            cmd.append('--scrape-only')
        elif mode == 'analyze':
            cmd.extend(['--analyze-only', str(PROJECT_ROOT / 'data' / 'scraped' / data_file)])
        elif mode == 'track':
            cmd.append('--track-only')
        if reset_cache:
            cmd.append('--reset-cache')
        if mode in ('full', 'scrape'):
            cmd.extend(['--scraper', scraper])

        _env = os.environ.copy()
        _env['ANTHROPIC_API_KEY'] = os.getenv('ANTHROPIC_API_KEY', '')
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=str(PROJECT_ROOT), env=_env
        )
        for line in proc.stdout:
            yield f'data: {line.rstrip()}\n\n'
        proc.wait()
        yield f'data: __done__\n\n'

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/docs/')
@app.route('/docs/<path:filename>')
def serve_docs(filename='getting-started.md'):
    docs_dir = PROJECT_ROOT / 'docs'
    doc_path = docs_dir / filename
    if not doc_path.exists() or doc_path.suffix != '.md':
        files = sorted(docs_dir.glob('*.md')) if docs_dir.exists() else []
        links = ''.join(
            f'<li><a href="/docs/{f.name}">{f.stem.replace("-", " ").title()}</a></li>'
            for f in files
        )
        return f'<html><body style="font-family:monospace;padding:24px"><h2>Documentation</h2><ul>{links}</ul></body></html>'

    content = doc_path.read_text()
    import html as html_mod, re as _re
    lines = []
    in_code = False
    for line in content.splitlines():
        if line.startswith('```'):
            lines.append('</pre>' if in_code else '<pre style="background:#1a1a1a;color:#00ff41;padding:12px;overflow-x:auto">')
            in_code = not in_code
            continue
        if in_code:
            lines.append(html_mod.escape(line))
            continue
        line = html_mod.escape(line)
        if line.startswith('### '):
            line = f'<h3>{line[4:]}</h3>'
        elif line.startswith('## '):
            line = f'<h2>{line[3:]}</h2>'
        elif line.startswith('# '):
            line = f'<h1>{line[2:]}</h1>'
        elif line.startswith('- '):
            line = f'<li>{line[2:]}</li>'
        elif line == '':
            line = '<br>'
        line = _re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
        line = _re.sub(r'`(.+?)`', r'<code style="background:#1a1a1a;padding:2px 4px">\1</code>', line)
        lines.append(line)

    body = '\n'.join(lines)
    return f'''<html><head><title>ApplicationAgent Docs</title>
    <style>body{{font-family:monospace;padding:32px 48px;background:#0d0d0d;color:#e0e0e0;max-width:860px}}
    h1,h2,h3{{color:#00ff41}} a{{color:#00b32c}} li{{margin:4px 0}}</style></head>
    <body><p><a href="/docs/">← Docs index</a></p>{body}</body></html>'''


if __name__ == '__main__':
    from waitress import serve
    port = int(os.environ.get('FLASK_TEST_PORT', 8080))
    print("ApplicationAgent UI")
    print(f"Open: http://localhost:{port}")
    serve(app, host='0.0.0.0', port=port, threads=8)
