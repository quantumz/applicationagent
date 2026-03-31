"""
ApplicationAgent - Personal Job Screening Agent
Analyzes job postings to determine if you should apply.

Screens jobs for YOU - saving time on applications that won't pass ATS.
"""

import os
from datetime import datetime
from dotenv import load_dotenv
from anthropic import Anthropic
import json
import re

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def analyze_job_fit(job_description, resume_text, resume_type="default", location_preferences=None):
    """
    Main fit analysis function

    Args:
        job_description: The job posting text
        resume_text: Your resume as plain text
        resume_type: Resume identifier (used as context label in AI prompt)
        location_preferences: List of acceptable location strings (e.g. ["Portland", "Remote"]).
                              If None, all locations are considered compatible.

    Returns:
        Dict with fit analysis results
    """
    print(f"\n{'='*60}")
    print(f"ANALYZING JOB FIT")
    print(f"Resume Type: {resume_type.upper()}")
    print(f"{'='*60}")

    quick_analysis = perform_quick_checks(job_description, resume_text, location_preferences)
    ai_analysis = perform_ai_fit_analysis(job_description, resume_text, resume_type)
    fit_score = calculate_fit_score(quick_analysis, ai_analysis)

    role_fit = ai_analysis.get('role_fit', 'UNKNOWN')
    if role_fit == 'POOR' and fit_score >= 0.70:
        decision = "ATS_ONLY"
    elif fit_score >= 0.90:
        decision = "STRONG_MATCH"
    elif fit_score >= 0.70:
        decision = "APPLY"
    elif fit_score >= 0.50:
        decision = "MAYBE"
    else:
        decision = "SKIP"

    result = {
        'decision': decision,
        'fit_score': fit_score,
        'quick_analysis': quick_analysis,
        'ai_analysis': ai_analysis,
        'timestamp': datetime.now().isoformat(),
        'resume_type': resume_type
    }

    print_analysis_summary(result)
    return result


def perform_quick_checks(job_description, resume_text, location_preferences=None):
    """
    Fast local checks before the API call.

    location_preferences: list of strings to match against job text (case-insensitive).
                         Pass None to skip location filtering (all jobs pass).
    """
    checks = {
        'title_match': False,
        'senior_level_match': False,
        'location_compatible': False,
        'obvious_dealbreakers': []
    }

    job_lower = job_description.lower()
    resume_lower = resume_text.lower()

    # Title match — check if job domain aligns with resume domain
    # TODO: title_match is driven by hardcoded domain keyword lists — should be derived
    #       dynamically from resume content so any domain works without code changes.
    devops_keywords = ['devops', 'sre', 'site reliability', 'platform engineer', 'cloud engineer']
    if any(kw in job_lower for kw in devops_keywords):
        if any(kw in resume_lower for kw in devops_keywords):
            checks['title_match'] = True

    # am_keywords = ['additive manufacturing', '3d print', 'am engineer', 'manufacturing operations']
    # if any(kw in job_lower for kw in am_keywords):
    #     if any(kw in resume_lower for kw in am_keywords):
    #         checks['title_match'] = True

    # Seniority check
    senior_indicators = ['senior', 'staff', 'principal', 'lead', '10+ years', '15+ years']
    if any(indicator in job_lower for indicator in senior_indicators):
        checks['senior_level_match'] = True

    # Location check
    if location_preferences:
        checks['location_compatible'] = any(loc.lower() in job_lower for loc in location_preferences)
    else:
        # No preference configured — treat all locations as compatible
        checks['location_compatible'] = True

    # Dealbreakers
    # TODO: move hardcoded dealbreakers into per-resume _search_criteria.json as
    #       'dealbreaker_keywords' — NOT scraper_config.json (wrong layer: scraper
    #       filters what gets fetched; dealbreakers affect scoring after fetch).
    #       A dedicated agent_config.json for global defaults is a valid alternative.
    dealbreakers = []
    if 'relocation required' in job_lower and 'remote' not in job_lower:
        dealbreakers.append("Relocation required (not remote)")
    if 'clearance' in job_lower or 'security clearance' in job_lower:
        dealbreakers.append("Security clearance required")


    checks['obvious_dealbreakers'] = dealbreakers

    return checks


def perform_ai_fit_analysis(job_description, resume_text, resume_type):
    """
    Use Anthropic API to perform deep fit analysis.
    Returns dict with AI analysis results.
    """
    print("  🤖 Running AI fit analysis...")

    current_date = datetime.now().strftime("%B %Y")

    prompt = f"""Analyze if this candidate should apply for this job. Be brutally honest.

CURRENT DATE: {current_date}

JOB DESCRIPTION:
{job_description}

CANDIDATE RESUME (Type: {resume_type}):
{resume_text}

Analyze for:

1. **Keyword Match**: Does the resume contain the technical skills mentioned in the job?
   - List matching keywords
   - List missing critical keywords
   - Are there alternate terms for the same skills?

2. **Experience Level Match**:
   - Is the candidate over/under/appropriately qualified?
   - Does years of experience align with requirements?
   - Is the seniority level appropriate?

3. **ATS Compatibility**:
   - Will automated keyword screening likely pass this resume?
   - Are there formatting or terminology mismatches?
   - Does the resume "speak the same language" as the job description?

4. **Role Fit**:
   - Does the candidate's background make sense for this role?
   - Is this a lateral move, step up, or career change?
   - Are there red flags (overqualified, underqualified, wrong domain)?

5. **Competitive Position**:
   - How strong is this candidate vs typical applicants?
   - What are the standout strengths?
   - What are the gaps that could disqualify them?

6. **Application Strategy**:
   - Should they apply?
   - If yes, what should they emphasize in cover letter?
   - If no, what's missing?

7. **Interview Process Red Flags** (if mentioned in job description):
   - Multi-round coding tests (more than 2 rounds)
   - Unpaid "homework assignments" or take-home projects >4 hours
   - Live coding on phone screens
   - Leetcode/algorithm focus for senior roles
   - Excessive interview rounds (>5 total)
   - Whiteboard coding for experienced engineers
   - "Culture fit" assessments (arbitrary/subjective)

8. **Interview Process Green Flags** (if mentioned):
   - Conversation-based technical discussions
   - "Show us something you've built" approach
   - Collaborative pair programming
   - Reasonable take-home with paid time
   - Focus on systems design over algorithms
   - Respectful of candidate's time

Return your analysis in this JSON format:
{{
  "keyword_matches": ["list of matching keywords"],
  "missing_keywords": ["list of critical missing keywords"],
  "experience_level": "OVER_QUALIFIED" | "APPROPRIATE" | "UNDER_QUALIFIED",
  "experience_reasoning": "brief explanation",
  "ats_pass_likelihood": "HIGH" | "MEDIUM" | "LOW",
  "ats_reasoning": "why it will/won't pass automated screening",
  "role_fit": "EXCELLENT" | "GOOD" | "FAIR" | "POOR",
  "role_fit_reasoning": "explanation of fit",
  "competitive_strengths": ["list of standout strengths"],
  "competitive_gaps": ["list of significant gaps"],
  "should_apply": "DEFINITELY" | "PROBABLY" | "MAYBE" | "NO",
  "application_strategy": "what to emphasize if applying, or why to skip",
  "interview_red_flags": ["list of concerning interview process signals, or empty if none mentioned"],
  "interview_green_flags": ["list of positive interview process signals, or empty if none mentioned"],
  "interview_warning": "SEVERE" | "MODERATE" | "MINIMAL" | "NONE",
  "interview_reasoning": "explanation of interview process concerns",
  "confidence": 0.0 to 1.0,
  "overall_reasoning": "detailed explanation of recommendation"
}}

Be honest. If the candidate won't get past ATS, say so. If they're wasting their time, say so.
"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text

        json_text = response_text.strip()
        if json_text.startswith('```'):
            match = re.search(r'```(?:json)?\s*(\{.*\})\s*```', json_text, re.DOTALL)
            if match:
                json_text = match.group(1)

        analysis = json.loads(json_text)

        print(f"  ✓ AI Analysis complete")
        print(f"    Recommendation: {analysis.get('should_apply')}")
        print(f"    ATS Likelihood: {analysis.get('ats_pass_likelihood')}")

        return analysis

    except Exception as e:
        print(f"  ❌ AI analysis failed: {e}")
        return {
            'keyword_matches': [],
            'missing_keywords': [],
            'experience_level': 'UNKNOWN',
            'experience_reasoning': f'Analysis failed: {str(e)}',
            'ats_pass_likelihood': 'UNKNOWN',
            'ats_reasoning': 'Error',
            'role_fit': 'UNKNOWN',
            'role_fit_reasoning': 'Error',
            'competitive_strengths': [],
            'competitive_gaps': [],
            'should_apply': 'ERROR',
            'application_strategy': f'Could not complete analysis: {str(e)}',
            'confidence': 0.0,
            'overall_reasoning': 'Analysis error'
        }


def calculate_fit_score(quick_analysis, ai_analysis):
    """
    Calculate overall fit score (0.0 = terrible fit, 1.0 = perfect fit).
    Combines quick checks and AI analysis into a single score.
    """
    score = 0.5  # Start neutral

    if quick_analysis['title_match']:
        score += 0.1
    if quick_analysis['senior_level_match']:
        score += 0.05
    if quick_analysis['location_compatible']:
        score += 0.05

    if quick_analysis['obvious_dealbreakers']:
        score -= 0.2 * len(quick_analysis['obvious_dealbreakers'])

    should_apply = ai_analysis.get('should_apply', 'MAYBE')
    if should_apply == 'DEFINITELY':
        score += 0.3
    elif should_apply == 'PROBABLY':
        score += 0.15
    elif should_apply == 'NO':
        score -= 0.2

    ats_likelihood = ai_analysis.get('ats_pass_likelihood', 'MEDIUM')
    if ats_likelihood == 'HIGH':
        score += 0.15
    elif ats_likelihood == 'LOW':
        score -= 0.15

    exp_level = ai_analysis.get('experience_level', 'APPROPRIATE')
    if exp_level == 'APPROPRIATE':
        score += 0.1
    elif exp_level == 'OVER_QUALIFIED':
        score -= 0.05
    elif exp_level == 'UNDER_QUALIFIED':
        score -= 0.15

    interview_warning = ai_analysis.get('interview_warning', 'NONE')
    if interview_warning == 'SEVERE':
        score -= 0.3
    elif interview_warning == 'MODERATE':
        score -= 0.15
    elif interview_warning == 'MINIMAL':
        score -= 0.05

    # ROLE FIT HARD GATE — caps score below action thresholds when fit is poor/fair
    role_fit = ai_analysis.get('role_fit', 'UNKNOWN')
    if role_fit == 'POOR':
        score = min(score, 0.65)
    elif role_fit == 'FAIR':
        score = min(score, 0.65)   # Below APPLY threshold — shows as MAYBE
    # GOOD / EXCELLENT: no cap

    return max(0.0, min(1.0, score))


def print_analysis_summary(result):
    """Print human-readable summary of analysis"""
    print(f"\n{'='*60}")
    print(f"JOB FIT ANALYSIS RESULTS")
    print(f"{'='*60}")
    print(f"Decision: {result['decision']}")
    print(f"Fit Score: {result['fit_score']:.2f} (0.0=skip, 1.0=perfect)")
    print(f"Resume Type: {result['resume_type']}")

    ai = result['ai_analysis']
    print(f"\nAI Recommendation: {ai.get('should_apply')}")
    print(f"ATS Pass Likelihood: {ai.get('ats_pass_likelihood')}")
    print(f"Experience Level: {ai.get('experience_level')}")
    print(f"Role Fit: {ai.get('role_fit')}")
    print(f"Confidence: {ai.get('confidence', 0):.0%}")

    interview_warning = ai.get('interview_warning', 'NONE')
    if interview_warning != 'NONE':
        print(f"\n{'!'*60}")
        print(f"⚠️  INTERVIEW PROCESS WARNING: {interview_warning}")
        print(f"{'!'*60}")
        print(f"{ai.get('interview_reasoning', 'See details below')}")

    if ai.get('interview_red_flags'):
        print(f"\n🚨 INTERVIEW RED FLAGS:")
        for flag in ai['interview_red_flags']:
            print(f"  - {flag}")
        print(f"\n⚠️  These will likely cause you to walk out or waste your time.")

    if ai.get('interview_green_flags'):
        print(f"\n✅ INTERVIEW GREEN FLAGS:")
        for flag in ai['interview_green_flags']:
            print(f"  - {flag}")

    if ai.get('competitive_strengths'):
        print(f"\n✓ STRENGTHS:")
        for strength in ai['competitive_strengths']:
            print(f"  - {strength}")

    if ai.get('competitive_gaps'):
        print(f"\n⚠️  GAPS:")
        for gap in ai['competitive_gaps']:
            print(f"  - {gap}")

    if ai.get('missing_keywords'):
        print(f"\n❌ MISSING KEYWORDS:")
        for keyword in ai['missing_keywords']:
            print(f"  - {keyword}")

    if result['quick_analysis']['obvious_dealbreakers']:
        print(f"\n🚫 DEALBREAKERS:")
        for db in result['quick_analysis']['obvious_dealbreakers']:
            print(f"  - {db}")

    print(f"\nStrategy: {ai.get('application_strategy', 'N/A')}")
    print(f"\nReasoning: {ai.get('overall_reasoning', 'N/A')}")
    print(f"{'='*60}\n")
