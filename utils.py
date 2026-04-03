# utils.py - Shared utility functions for bill analysis
import io
import os
import re
import json
import urllib3
import warnings
import requests
from pdfminer.high_level import extract_text

# -----------------------------
# Configuration
# -----------------------------
CURRENT_SESSION = os.environ.get('TX_LEGISLATURE_SESSION', '89R')
TELICON_BASE_URL = "https://www.telicon.com/www/TX"

# Heroku Managed Inference Configuration
INFERENCE_URL = os.environ.get('INFERENCE_URL')
INFERENCE_KEY = os.environ.get('INFERENCE_KEY')
INFERENCE_MODEL_ID = os.environ.get('INFERENCE_MODEL_ID')

# -----------------------------
# Telicon Request Helper
# -----------------------------
def _telicon_request(method, url, **kwargs):
    """Make a request to Telicon with SSL verification disabled (self-signed cert).
    Suppresses InsecureRequestWarning only for these calls."""
    kwargs['verify'] = False
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', urllib3.exceptions.InsecureRequestWarning)
        return getattr(requests, method)(url, **kwargs)

# -----------------------------
# PDF Processing Functions
# -----------------------------
def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract plain text from PDF bytes."""
    try:
        with io.BytesIO(pdf_bytes) as fh:
            txt = extract_text(fh) or ""
            txt = re.sub(r"[ \t]+", " ", txt)
            txt = re.sub(r"\n{3,}", "\n\n", txt).strip()
            return txt
    except Exception as e:
        print(f"[ERROR] PDF extraction failed: {e}")
        return ""

def get_appropriate_text_limit(text: str) -> int:
    """Dynamically adjust text limit based on content size."""
    length = len(text)
    if length < 50000:
        return min(length, 10000)
    elif length < 100000:
        return 8000
    elif length < 150000:
        return 6000
    else:
        return 4000

# -----------------------------
# Bill Lookup Functions
# -----------------------------
def parse_bill_number(bill_number: str) -> tuple:
    """Parse bill number into (bill_type, bill_num)."""
    match = re.match(r"([HS][BRJ])\s*(\d+)", bill_number.upper().strip())
    if not match:
        return None, None

    bill_type = match.group(1)
    bill_num = match.group(2).zfill(5)
    return bill_type, bill_num

def try_bill_url_patterns(bill_type: str, bill_num: str, session: str) -> tuple:
    """Try multiple URL patterns until one works."""
    patterns = [
        {
            "url": f"{TELICON_BASE_URL}/{session}/pdf/TX{session}{bill_type}{bill_num}FIL.pdf",
            "type": "primary"
        },
        {
            "url": f"{TELICON_BASE_URL}/{session}/pdf/{bill_type}{bill_num}FIL.pdf",
            "type": "fallback_no_session_in_name"
        },
        {
            "url": f"{TELICON_BASE_URL}/{session}/bills/TX{session}{bill_type}{bill_num}.pdf",
            "type": "fallback_bills_dir"
        },
        {
            "url": f"{TELICON_BASE_URL}/bills/{session}/{bill_type}{bill_num}.pdf",
            "type": "fallback_flat"
        }
    ]

    for pattern in patterns:
        try:
            response = _telicon_request('head', pattern["url"], timeout=5)
            if response.status_code == 200:
                print(f"[SUCCESS] Found bill using {pattern['type']}")
                return pattern["url"], pattern["type"]
        except:
            continue

    return None, None

def try_fiscal_note_patterns(bill_type: str, bill_num: str, session: str) -> tuple:
    """Try multiple fiscal note URL patterns."""
    patterns = [
        {
            "url": f"{TELICON_BASE_URL}/{session}/fnote/TX{session}{bill_type}{bill_num}FIL.pdf",
            "type": "primary"
        },
        {
            "url": f"{TELICON_BASE_URL}/{session}/fnote/{bill_type}{bill_num}FIL.pdf",
            "type": "fallback_no_session_in_name"
        },
        {
            "url": f"{TELICON_BASE_URL}/{session}/fiscal/{bill_type}{bill_num}.pdf",
            "type": "fallback_fiscal_dir"
        }
    ]

    for pattern in patterns:
        try:
            response = _telicon_request('head', pattern["url"], timeout=5)
            if response.status_code == 200:
                print(f"[SUCCESS] Found fiscal note using {pattern['type']}")
                return pattern["url"], pattern["type"]
        except:
            continue

    return None, None

def should_fetch_fiscal_note(bill_text: str) -> bool:
    """Determine if fiscal note is relevant based on bill content."""
    fiscal_keywords = [
        "appropriation", "funding", "budget", "fiscal impact",
        "cost", "revenue", "expenditure", "million", "billion",
        "grant", "allocation", "financial"
    ]

    bill_text_lower = bill_text.lower()
    return any(keyword in bill_text_lower for keyword in fiscal_keywords)

# -----------------------------
# Claude AI Functions
# -----------------------------
def extract_fiscal_data_with_claude(fiscal_note_text: str, timeout: int = 60) -> dict:
    """
    Use Claude to extract structured fiscal data from the fiscal note.
    VERSION 9.2 - Improved prompt with clearer structure and instructions.

    Args:
        fiscal_note_text: Raw text of the fiscal note.
        timeout: Request timeout in seconds (default 60, use higher for background jobs).
    """
    if not fiscal_note_text:
        return {"fiscal_note_summary": "", "total_fiscal_impact": 0}

    if not all([INFERENCE_URL, INFERENCE_KEY, INFERENCE_MODEL_ID]):
        print('[WARN] Heroku Managed Inference not configured')
        return {
            "fiscal_note_summary": fiscal_note_text[:3000],
            "total_fiscal_impact": 0
        }

    try:
        text_limit = get_appropriate_text_limit(fiscal_note_text)

        prompt = f"""Analyze this Texas fiscal note and extract key financial data.

Return ONLY valid JSON (no markdown, no code blocks):
{{
  "fiscal_note_summary": "Your 3-paragraph summary here",
  "total_fiscal_impact": -1234567.89
}}

WRITE 3 CLEAR PARAGRAPHS:

Paragraph 1 - Bottom Line (2-3 sentences):
State the total five-year fiscal impact as a dollar amount. Say if this is significant, moderate, or minimal for Texas. Mention if it uses static or dynamic scoring (if stated).

Paragraph 2 - Year-by-Year Breakdown (3-4 sentences):
List the specific amount for each fiscal year (e.g., "FY2026: -$4.1B, FY2027: -$4.4B"). Break down by fund source (General Revenue, Federal Funds, etc.). Note which costs are one-time vs. recurring.

Paragraph 3 - Implementation Details (2-3 sentences):
How many new FTEs (full-time employees) are needed and at what cost? What's the implementation timeline? Any important assumptions or conditions?

TOTAL FISCAL IMPACT NUMBER:
- Add up ALL fiscal years in the note
- Use NEGATIVE for costs/expenses: -1234567.89
- Use POSITIVE for revenue/savings: +1234567.89
- If there's no clear total stated, calculate it from the year-by-year amounts

Be specific with actual dollar amounts. Write in clear, professional language.

Fiscal Note (first {text_limit} chars):
{fiscal_note_text[:text_limit]}"""

        headers = {
            'Authorization': f'Bearer {INFERENCE_KEY}',
            'Content-Type': 'application/json'
        }

        payload = {
            'model': INFERENCE_MODEL_ID,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.1,
            'max_tokens': 2500
        }

        response = requests.post(
            f'{INFERENCE_URL}/v1/chat/completions',
            headers=headers,
            json=payload,
            timeout=timeout
        )

        if response.status_code != 200:
            print(f'[ERROR] Fiscal extraction failed: {response.status_code}')
            return {
                "fiscal_note_summary": fiscal_note_text[:3000],
                "total_fiscal_impact": 0
            }

        response_data = response.json()
        response_text = response_data['choices'][0]['message']['content'].strip()

        # Clean markdown if present
        if response_text.startswith('```'):
            lines = response_text.split('\n')
            response_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_text
            if response_text.startswith('json'):
                response_text = response_text[4:].strip()

        result = json.loads(response_text)
        print(f'[SUCCESS] Extracted fiscal data: ${result.get("total_fiscal_impact", 0):,.2f}')
        return result

    except json.JSONDecodeError as e:
        print(f'[ERROR] JSON parsing failed: {e}')
        return {
            "fiscal_note_summary": fiscal_note_text[:3000],
            "total_fiscal_impact": 0
        }
    except Exception as e:
        print(f'[ERROR] Fiscal extraction failed: {e}')
        return {
            "fiscal_note_summary": fiscal_note_text[:3000],
            "total_fiscal_impact": 0
        }
