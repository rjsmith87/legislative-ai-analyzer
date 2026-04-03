# app.py - VERSION 9.2 - IMPROVED PROMPTS + BETTER FORMATTING
import hmac
import io
import logging
import os
import re
import json
import urllib3
import warnings
from functools import wraps
from flask import Flask, request, jsonify
import requests
from datetime import datetime
from rq import Queue
from rq.job import Job
import redis

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

from utils import (
    CURRENT_SESSION,
    TELICON_BASE_URL,
    INFERENCE_URL,
    INFERENCE_KEY,
    INFERENCE_MODEL_ID,
    _telicon_request,
    extract_text_from_pdf_bytes,
    get_appropriate_text_limit,
    parse_bill_number,
    try_bill_url_patterns,
    try_fiscal_note_patterns,
    should_fetch_fiscal_note,
    extract_fiscal_data_with_claude,
)

app = Flask(__name__)

# -----------------------------
# API Key Authentication
# -----------------------------
def require_api_key(f):
    """Decorator that checks for a valid API key on requests.
    If the API_KEY env var is not set, all requests are allowed (local dev).
    The /health endpoint is exempt (registered separately).
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        server_key = os.environ.get('API_KEY')
        if not server_key:
            # No API_KEY configured -- allow all requests (local dev)
            return f(*args, **kwargs)

        # Accept key from X-API-Key header or Authorization: Bearer <key>
        provided_key = request.headers.get('X-API-Key', '')
        if not provided_key:
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                provided_key = auth_header[7:]

        if not provided_key or not hmac.compare_digest(provided_key, server_key):
            return jsonify({"error": "Unauthorized"}), 401

        return f(*args, **kwargs)
    return decorated

# -----------------------------
# Redis / Cache Configuration
# -----------------------------
redis_client = None
redis_job_client = None
CACHE_ENABLED = False

try:
    redis_url = os.environ.get('REDIS_URL')
    if redis_url:
        # Cache client - WITH decode_responses
        redis_client = redis.from_url(
            redis_url,
            decode_responses=True,
            ssl_cert_reqs=None
        )
        redis_client.ping()

        # Job client - WITHOUT decode_responses (for RQ)
        redis_job_client = redis.from_url(
            redis_url,
            ssl_cert_reqs=None
        )

        CACHE_ENABLED = True
        logger.info('Redis cache enabled')
except Exception as e:
    logger.warning('Redis not available: %s', e)
    redis_client = None
    redis_job_client = None

# Job Queue for background processing
job_queue = None
if CACHE_ENABLED and redis_job_client:
    try:
        job_queue = Queue('default', connection=redis_job_client)
        logger.info('Job queue enabled')
    except Exception as e:
        logger.warning('Job queue not available: %s', e)

# -----------------------------
# Cache Helper Functions
# -----------------------------
def get_cache_key(bill_number: str, session: str) -> str:
    """Generate consistent cache key for bill analysis."""
    match = re.match(r"([HS][BRJ])\s*(\d+)", bill_number.upper().strip())
    if match:
        bill_type = match.group(1)
        bill_num = match.group(2).zfill(5)
        normalized = f"{bill_type}{bill_num}"
    else:
        normalized = bill_number.upper().replace(' ', '')

    return f"bill_analysis:{session}:{normalized}"

def get_cached_analysis(bill_number: str, session: str) -> dict:
    """Retrieve cached analysis if available."""
    if not CACHE_ENABLED:
        return None

    try:
        key = get_cache_key(bill_number, session)
        cached = redis_client.get(key)
        if cached:
            result = json.loads(cached)
            logger.info("Returning cached analysis for %s", bill_number)
            return result
    except Exception as e:
        logger.error("Cache failed to retrieve: %s", e)

    return None

def cache_analysis(bill_number: str, session: str, data: dict, ttl: int = 86400):
    """Store analysis in cache (24 hour TTL by default)."""
    if not CACHE_ENABLED:
        return

    try:
        key = get_cache_key(bill_number, session)
        redis_client.setex(key, ttl, json.dumps(data))
        redis_client.set('last_success_timestamp', datetime.utcnow().isoformat())
        redis_client.set('last_success_bill', bill_number)
        logger.info("Cached analysis for %s (TTL: %ds)", bill_number, ttl)
    except Exception as e:
        logger.error("Cache failed to store: %s", e)

def invalidate_cache(bill_number: str, session: str):
    """Manually invalidate cache for a specific bill."""
    if not CACHE_ENABLED:
        return

    try:
        key = get_cache_key(bill_number, session)
        redis_client.delete(key)
        logger.info("Cache invalidated for %s", bill_number)
    except Exception as e:
        logger.error("Cache failed to invalidate: %s", e)

def get_cache_stats() -> dict:
    """Get cache statistics."""
    if not CACHE_ENABLED:
        return {"enabled": False}

    try:
        info = redis_client.info('stats')
        return {
            "enabled": True,
            "connected": True,
            "keyspace_hits": info.get('keyspace_hits', 0),
            "keyspace_misses": info.get('keyspace_misses', 0),
            "last_success": redis_client.get('last_success_timestamp'),
            "last_bill": redis_client.get('last_success_bill')
        }
    except:
        return {"enabled": True, "connected": False}

# -----------------------------
# CLAUDE FUNCTIONS - IMPROVED PROMPTS
# -----------------------------
def generate_bill_summary(bill_text: str, bill_number: str) -> str:
    """
    Use Claude to generate a concise 2-3 sentence bill summary.
    VERSION 9.2 - Improved prompt for clearer, more useful summaries.
    """
    if not all([INFERENCE_URL, INFERENCE_KEY, INFERENCE_MODEL_ID]):
        # Fallback: extract first meaningful sentence
        sentences = bill_text[:500].split('.')
        return sentences[0] if sentences else "Bill analysis unavailable."

    try:
        prompt = f"""Analyze this Texas bill and write a clear 2-3 sentence summary for a general audience.

Focus on:
1. What the bill DOES (creates, modifies, funds, prohibits, requires)
2. Who it AFFECTS (specific groups: teachers, businesses, taxpayers, etc.)
3. Why it MATTERS (the practical impact)

Avoid legal jargon. Write like you're explaining it to a friend.

Bill {bill_number}:
{bill_text[:2500]}

Summary:"""

        headers = {
            'Authorization': f'Bearer {INFERENCE_KEY}',
            'Content-Type': 'application/json'
        }

        payload = {
            'model': INFERENCE_MODEL_ID,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.3,
            'max_tokens': 250
        }

        response = requests.post(
            f'{INFERENCE_URL}/v1/chat/completions',
            headers=headers,
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            response_data = response.json()
            summary = response_data['choices'][0]['message']['content'].strip()
            # Remove "Summary:" prefix if Claude includes it
            summary = re.sub(r'^Summary:\s*', '', summary, flags=re.IGNORECASE)
            logger.info('Generated bill summary for %s', bill_number)
            return summary
        else:
            logger.warning('Summary generation failed: %s', response.status_code)
            return f"Analysis of {bill_number} relating to Texas legislation."

    except Exception as e:
        logger.error('Bill summary generation failed: %s', e)
        return f"Analysis of {bill_number} relating to Texas legislation."

def format_complete_response(
    bill_number: str,
    bill_summary: str,
    fiscal_note_summary: str,
    total_fiscal_impact: float,
    fiscal_note_url: str
) -> str:
    """
    Format the complete response with better visual presentation.
    VERSION 9.2 - Improved formatting and clarity
    """

    # Smart fiscal formatting
    if total_fiscal_impact < 0:
        abs_val = abs(total_fiscal_impact)
        if abs_val >= 1_000_000_000:
            impact_str = f"-${abs_val/1_000_000_000:.2f} billion"
        elif abs_val >= 1_000_000:
            impact_str = f"-${abs_val/1_000_000:.2f} million"
        else:
            impact_str = f"-${abs_val:,.0f}"
    elif total_fiscal_impact > 0:
        if total_fiscal_impact >= 1_000_000_000:
            impact_str = f"+${total_fiscal_impact/1_000_000_000:.2f} billion"
        elif total_fiscal_impact >= 1_000_000:
            impact_str = f"+${total_fiscal_impact/1_000_000:.2f} million"
        else:
            impact_str = f"+${total_fiscal_impact:,.0f}"
    else:
        impact_str = "No fiscal impact"

    # Build cleaner response
    if fiscal_note_summary:
        formatted = f"""📊 BILL ANALYSIS: {bill_number}

SUMMARY
{bill_summary}

💰 FISCAL IMPACT

{fiscal_note_summary}

Five-Year Total: {impact_str}

📎 View the full fiscal note: {fiscal_note_url}

Would you like to save this bill to Salesforce for tracking?"""
    else:
        formatted = f"""📊 BILL ANALYSIS: {bill_number}

SUMMARY
{bill_summary}

💰 FISCAL IMPACT
No fiscal analysis is currently available for this bill.

Would you like to save this bill to Salesforce for tracking?"""

    return formatted

# -----------------------------
# Core Analysis Logic (Shared)
# -----------------------------
def perform_bill_analysis(bill_number: str, session: str = None) -> dict:
    """
    Core bill analysis logic that can be called by multiple endpoints.
    VERSION 9.2 - Uses improved Claude prompts
    """
    if session is None:
        session = CURRENT_SESSION

    bill_type, bill_num = parse_bill_number(bill_number)
    if not bill_type or not bill_num:
        return {
            "error": "Invalid bill format. Use format like 'HB 150' or 'SB 2'",
            "error_code": "INVALID_BILL_FORMAT",
            "success": False
        }

    formatted_bill = f"{bill_type}{bill_num}"

    # Try to find bill
    bill_url, bill_pattern = try_bill_url_patterns(bill_type, bill_num, session)

    if not bill_url:
        return {
            "bill_number": formatted_bill,
            "session": session,
            "exists": False,
            "success": False,
            "error": "Bill not found in Telicon system",
            "error_code": "BILL_NOT_FOUND"
        }

    # Fetch bill PDF
    try:
        logger.info("Fetching bill from: %s", bill_url)
        bill_response = _telicon_request('get', bill_url, timeout=30)
        if bill_response.status_code != 200:
            return {
                "error": f"Failed to fetch bill (HTTP {bill_response.status_code})",
                "error_code": "BILL_FETCH_FAILED",
                "success": False
            }
    except requests.exceptions.Timeout:
        return {
            "error": "Bill fetch timed out",
            "error_code": "TIMEOUT",
            "success": False
        }
    except Exception as e:
        return {
            "error": str(e),
            "error_code": "BILL_FETCH_ERROR",
            "success": False
        }

    # Extract bill text
    bill_text = extract_text_from_pdf_bytes(bill_response.content)
    if not bill_text:
        return {
            "error": "Could not extract bill text from PDF",
            "error_code": "PDF_EXTRACTION_FAILED",
            "success": False
        }

    logger.info("Extracted %d characters from bill", len(bill_text))

    # Generate bill summary using Claude (IMPROVED PROMPT)
    bill_summary = generate_bill_summary(bill_text, formatted_bill)

    # Check for and process fiscal note
    fiscal_relevant = should_fetch_fiscal_note(bill_text)
    fiscal_url = None
    fiscal_note_summary = ""
    total_fiscal_impact = 0

    if fiscal_relevant:
        fiscal_url, fiscal_pattern = try_fiscal_note_patterns(bill_type, bill_num, session)

        if fiscal_url:
            try:
                logger.info("Fetching fiscal note from: %s", fiscal_url)
                fiscal_response = _telicon_request('get', fiscal_url, timeout=15)
                if fiscal_response.status_code == 200:
                    fiscal_text = extract_text_from_pdf_bytes(fiscal_response.content)
                    if fiscal_text:
                        logger.info("Extracted %d characters from fiscal note", len(fiscal_text))
                        # Extract structured fiscal data using Claude (IMPROVED PROMPT)
                        fiscal_data = extract_fiscal_data_with_claude(fiscal_text)
                        fiscal_note_summary = fiscal_data.get('fiscal_note_summary', '')
                        total_fiscal_impact = fiscal_data.get('total_fiscal_impact', 0)
            except Exception as e:
                logger.warning("Fiscal note fetch failed: %s", e)

    # Generate the FORMATTED RESPONSE for Agentforce (IMPROVED FORMAT)
    formatted_response = format_complete_response(
        formatted_bill,
        bill_summary,
        fiscal_note_summary,
        total_fiscal_impact,
        fiscal_url or "No fiscal note available"
    )

    # Build complete result
    result = {
        "bill_number": formatted_bill,
        "bill_type": bill_type,
        "session": session,
        "bill_url": bill_url,
        "fiscal_note_url": fiscal_url,
        "bill_text": bill_text[:3000],
        "fiscal_note_summary": fiscal_note_summary,
        "total_fiscal_impact": total_fiscal_impact,
        "has_fiscal_note": bool(fiscal_note_summary),
        "formatted_response": formatted_response,
        "exists": True,
        "success": True,
        "timestamp": datetime.utcnow().isoformat()
    }

    return result

# -----------------------------
# API Routes
# -----------------------------
@app.route("/health", methods=["GET"])
def health():
    """Health check with full system status. Exempt from API key auth."""
    cache_stats = get_cache_stats()

    return jsonify({
        "ok": True,
        "service": "Texas Bill Analyzer",
        "version": "9.2.0",
        "features": {
            "formatted_responses": True,
            "agentforce_endpoint": True,
            "improved_prompts": True,
            "ai_enabled": bool(INFERENCE_URL),
            "redis_caching": CACHE_ENABLED,
            "background_jobs": job_queue is not None
        },
        "endpoints": [
            "/health",
            "/session",
            "/analyzeBill",
            "/analyzeBillForAgentforce",
            "/job/<job_id>",
            "/cache/stats",
            "/cache/invalidate"
        ],
        "cache_stats": cache_stats,
        "heroku_slug": os.environ.get('HEROKU_SLUG_COMMIT', 'unknown')[:7]
    })

@app.route("/session", methods=["GET"])
@require_api_key
def get_current_session():
    """Return current legislative session."""
    return jsonify({
        "session": CURRENT_SESSION,
        "session_year": "2025-2026" if CURRENT_SESSION == "89R" else "Unknown",
        "chamber": "Texas Legislature"
    })

@app.route("/cache/stats", methods=["GET"])
@require_api_key
def cache_stats():
    """Get cache statistics."""
    return jsonify(get_cache_stats())

@app.route("/cache/invalidate", methods=["POST"])
@require_api_key
def cache_invalidate():
    """Invalidate cache for a specific bill."""
    payload = request.get_json(silent=True) or {}
    bill_number = payload.get("bill_number")

    if not bill_number:
        return jsonify({"error": "bill_number is required"}), 400

    session = payload.get("session", CURRENT_SESSION)
    invalidate_cache(bill_number, session)

    return jsonify({
        "success": True,
        "message": f"Cache invalidated for {bill_number}"
    })

@app.route("/job/<job_id>", methods=["GET"])
@require_api_key
def get_job_status(job_id):
    """Check status of background job."""
    if not CACHE_ENABLED or not job_queue or not redis_job_client:
        return jsonify({"error": "Jobs not available"}), 503

    try:
        job = Job.fetch(job_id, connection=redis_job_client)

        if job.is_finished:
            result = job.result
            if result and result.get('success'):
                cache_analysis(result['bill_number'], result['session'], result)
                logger.info("Job complete, cached result for %s", result['bill_number'])
            return jsonify({
                "status": "completed",
                "result": result
            })
        elif job.is_failed:
            return jsonify({
                "status": "failed",
                "error": str(job.exc_info)
            })
        else:
            return jsonify({
                "status": "processing",
                "job_id": job_id
            })
    except Exception as e:
        logger.error("Job fetch failed: %s", e)
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 404

@app.route("/analyzeBillForAgentforce", methods=["POST"])
@require_api_key
def analyze_bill_for_agentforce():
    """
    SIMPLIFIED ENDPOINT FOR AGENTFORCE
    Returns ONLY the formatted natural language response.
    VERSION 9.2 - Uses improved prompts and formatting
    """
    payload = request.get_json(silent=True) or {}
    bill_number = payload.get("bill_number")

    logger.info("Agentforce request for: %s", bill_number)

    if not bill_number:
        return jsonify({
            "response": "I need a bill number to analyze. Please provide a bill number like 'HB 150' or 'SB 2'.",
            "success": False
        }), 400

    session = CURRENT_SESSION

    # Check cache first
    cached_result = get_cached_analysis(bill_number, session)
    if cached_result and cached_result.get('formatted_response'):
        logger.info("Cache hit, returning formatted response for %s", bill_number)
        return jsonify({
            "response": cached_result['formatted_response'],
            "success": True
        })

    # Perform fresh analysis
    result = perform_bill_analysis(bill_number, session)

    # Handle errors
    if not result.get('success'):
        error_msg = result.get('error', 'Unknown error occurred')
        return jsonify({
            "response": f"I encountered an issue analyzing {bill_number}: {error_msg}",
            "success": False
        }), 400 if result.get('error_code') == 'INVALID_BILL_FORMAT' else 500

    # Cache the full result
    cache_analysis(bill_number, session, result)

    # Return ONLY the formatted response for Agentforce
    logger.info("Returning formatted response for %s", bill_number)
    return jsonify({
        "response": result['formatted_response'],
        "success": True
    })

@app.route("/analyzeBill", methods=["POST"])
@require_api_key
def analyze_bill():
    """
    FULL ANALYSIS ENDPOINT (Original)
    Returns complete structured data for Salesforce records.
    VERSION 9.2 - Uses improved prompts
    """
    payload = request.get_json(silent=True) or {}
    bill_number = payload.get("bill_number")
    force_refresh = payload.get("force_refresh", False)
    use_async = payload.get("use_async", False)

    logger.info("analyzeBill - Request for: %s", bill_number)

    if not bill_number:
        return jsonify({
            "error": "bill_number is required",
            "error_code": "MISSING_BILL_NUMBER",
            "success": False
        }), 400

    bill_type, bill_num = parse_bill_number(bill_number)
    if not bill_type or not bill_num:
        return jsonify({
            "error": "Invalid bill format. Use format like 'HB 150' or 'SB 2'",
            "error_code": "INVALID_BILL_FORMAT",
            "success": False
        }), 400

    session = CURRENT_SESSION
    formatted_bill = f"{bill_type}{bill_num}"

    # Check cache first
    if not force_refresh:
        cached_result = get_cached_analysis(bill_number, session)
        if cached_result:
            cached_result['cache_hit'] = True
            logger.info("Returning from cache for %s", bill_number)
            return jsonify(cached_result)

    # Determine if this should be a background job
    huge_bills = ['HB00002', 'SB00001', 'HB00001']
    should_async = use_async or (formatted_bill in huge_bills)

    if should_async and job_queue:
        from tasks import analyze_bill_task
        try:
            job = job_queue.enqueue(
                analyze_bill_task,
                bill_number,
                session,
                job_timeout='10m'
            )

            logger.info("Queued background job %s for %s", job.id, formatted_bill)

            return jsonify({
                "job_id": job.id,
                "status": "processing",
                "bill_number": formatted_bill,
                "check_url": f"/job/{job.id}",
                "message": "Large bill queued for background processing. Check status at /job/{job_id}",
                "success": True
            }), 202
        except Exception as e:
            logger.error("Failed to queue job: %s", e)
            # Fall through to synchronous processing

    # Perform analysis
    result = perform_bill_analysis(bill_number, session)

    # Handle errors
    if not result.get('success'):
        return jsonify(result), 404 if result.get('error_code') == 'BILL_NOT_FOUND' else 500

    # Add cache metadata
    result['cache_hit'] = False

    # Cache the result
    cache_analysis(bill_number, session, result)

    logger.info("Analysis complete for %s", formatted_bill)
    return jsonify(result)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    logger.info("Starting Texas Bill Analyzer v9.2 on port %d", port)
    logger.info("Legislative session: %s", CURRENT_SESSION)
    logger.info("AI formatting: %s", 'Enabled' if INFERENCE_URL else 'Disabled')
    logger.info("Redis caching: %s", 'Enabled' if CACHE_ENABLED else 'Disabled')
    logger.info("Background jobs: %s", 'Enabled' if job_queue else 'Disabled')
    logger.info("Agentforce endpoint: /analyzeBillForAgentforce")
    logger.info("API key auth: %s", 'Enabled' if os.environ.get('API_KEY') else 'Disabled (no API_KEY set)')
    logger.info("Version 9.2 - Improved prompts and formatting")
    app.run(host="0.0.0.0", port=port)
