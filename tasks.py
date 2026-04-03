# tasks.py - Background tasks for analyzing huge bills
import io
import os
import re
import json
import urllib3
import warnings
import requests
from pdfminer.high_level import extract_text
from datetime import datetime

CURRENT_SESSION = os.environ.get('TX_LEGISLATURE_SESSION', '89R')
TELICON_BASE_URL = "https://www.telicon.com/www/TX"

def _telicon_request(method, url, **kwargs):
    """Make a request to Telicon with SSL verification disabled (self-signed cert).
    Suppresses InsecureRequestWarning only for these calls."""
    kwargs['verify'] = False
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', urllib3.exceptions.InsecureRequestWarning)
        return getattr(requests, method)(url, **kwargs)

# Copy all helper functions from app.py
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
        return 4000  # Aggressive for huge bills

def extract_fiscal_summary_with_ai(fiscal_note_text: str) -> dict:
    """Use Claude to extract fiscal summary."""
    if not fiscal_note_text:
        return {"fiscal_note_summary": "", "total_fiscal_impact": 0}
    
    inference_url = os.environ.get('INFERENCE_URL')
    inference_key = os.environ.get('INFERENCE_KEY')
    inference_model = os.environ.get('INFERENCE_MODEL_ID')
    
    if not all([inference_url, inference_key, inference_model]):
        return {
            "fiscal_note_summary": fiscal_note_text[:3000],
            "total_fiscal_impact": 0
        }
    
    try:
        text_limit = get_appropriate_text_limit(fiscal_note_text)
        
        prompt = f"""Analyze this Texas legislative fiscal note and provide a comprehensive summary.

Return ONLY valid JSON (no markdown, no code blocks, no explanation):
{{
  "fiscal_note_summary": "Your summary here",
  "total_fiscal_impact": -1234567.89
}}

SUMMARY REQUIREMENTS (2-3 paragraphs):

Paragraph 1 - Overview:
- State the total net fiscal impact (positive for revenue/savings, negative for costs)
- Indicate whether impact is significant, moderate, or minimal
- Mention if methodology is dynamic or static scoring (if stated)

Paragraph 2 - Year-by-Year Breakdown:
- List specific amounts for each fiscal year (e.g., "FY2026: -$50.2M, FY2027: -$48.9M")
- Break down by fund type (General Revenue, Federal Funds, Special Funds, etc.)
- Distinguish between one-time and recurring costs

Paragraph 3 - Implementation Details:
- Staffing requirements: Number of FTEs and their annual costs
- Implementation timeline and milestones
- Any notable assumptions or contingencies
- Long-term sustainability considerations

TOTAL FISCAL IMPACT RULES:
- Sum ALL fiscal years mentioned in the note
- Use NEGATIVE numbers for costs/expenses (-1234567.89)
- Use POSITIVE numbers for revenue/savings (1234567.89)
- If no clear total, calculate from year-by-year data
- Include both one-time and recurring amounts

Be specific with dollar amounts and fiscal years. Use clear, professional language suitable for legislators.

Fiscal Note Text (first {text_limit} characters):
{fiscal_note_text[:text_limit]}"""
        
        headers = {
            'Authorization': f'Bearer {inference_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'model': inference_model,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.1,
            'max_tokens': 2500
        }
        
        response = requests.post(
            f'{inference_url}/v1/chat/completions',
            headers=headers,
            json=payload,
            timeout=120  # Longer timeout for background job
        )
        
        if response.status_code != 200:
            print(f'[ERROR] API call failed: {response.status_code}')
            return {
                "fiscal_note_summary": fiscal_note_text[:3000],
                "total_fiscal_impact": 0
            }
        
        response_data = response.json()
        response_text = response_data['choices'][0]['message']['content'].strip()
        
        # Remove markdown code blocks if present
        if response_text.startswith('```'):
            lines = response_text.split('\n')
            response_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_text
            if response_text.startswith('json'):
                response_text = response_text[4:].strip()
        
        result = json.loads(response_text)
        print(f'[SUCCESS] Claude generated fiscal summary: ${result.get("total_fiscal_impact", 0):,.2f}')
        return result
        
    except Exception as e:
        print(f'[ERROR] AI extraction failed: {e}')
        return {
            "fiscal_note_summary": fiscal_note_text[:3000],
            "total_fiscal_impact": 0
        }

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
    """Determine if fiscal note is relevant."""
    fiscal_keywords = [
        "appropriation", "funding", "budget", "fiscal impact",
        "cost", "revenue", "expenditure", "million", "billion",
        "grant", "allocation", "financial"
    ]
    
    bill_text_lower = bill_text.lower()
    return any(keyword in bill_text_lower for keyword in fiscal_keywords)

# Main background task
def analyze_bill_task(bill_number: str, session: str) -> dict:
    """
    Background task to analyze a bill - NO TIMEOUT!
    This runs in a worker dyno separate from the web dyno.
    """
    print(f"[BACKGROUND JOB] Starting analysis for {bill_number}")
    
    bill_type, bill_num = parse_bill_number(bill_number)
    if not bill_type or not bill_num:
        return {
            "error": "Invalid bill format",
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
            "error": "Bill not found"
        }
    
    # Fetch bill PDF
    try:
        print(f"[BACKGROUND JOB] Fetching bill from: {bill_url}")
        bill_response = _telicon_request('get', bill_url, timeout=60)
        if bill_response.status_code != 200:
            return {
                "error": "Failed to fetch bill",
                "success": False
            }
    except Exception as e:
        return {
            "error": str(e),
            "success": False
        }
    
    # Extract bill text
    bill_text = extract_text_from_pdf_bytes(bill_response.content)
    if not bill_text:
        return {
            "error": "Could not extract bill text",
            "success": False
        }
    
    print(f"[BACKGROUND JOB] Extracted {len(bill_text)} characters")
    
    # Check for fiscal note
    fiscal_relevant = should_fetch_fiscal_note(bill_text)
    fiscal_text = None
    fiscal_url = None
    fiscal_note_summary = ""
    total_fiscal_impact = 0
    
    if fiscal_relevant:
        fiscal_url, fiscal_pattern = try_fiscal_note_patterns(bill_type, bill_num, session)
        
        if fiscal_url:
            try:
                print(f"[BACKGROUND JOB] Fetching fiscal note from: {fiscal_url}")
                fiscal_response = _telicon_request('get', fiscal_url, timeout=30)
                if fiscal_response.status_code == 200:
                    fiscal_text = extract_text_from_pdf_bytes(fiscal_response.content)
                    if fiscal_text:
                        print(f"[BACKGROUND JOB] Fiscal note found: {len(fiscal_text)} characters")
                        # Get summary and total from Claude
                        fiscal_data = extract_fiscal_summary_with_ai(fiscal_text)
                        fiscal_note_summary = fiscal_data.get('fiscal_note_summary', '')
                        total_fiscal_impact = fiscal_data.get('total_fiscal_impact', 0)
            except Exception as e:
                print(f"[WARN] Fiscal note fetch failed: {e}")
    
    # Build result
    result = {
        "bill_number": formatted_bill,
        "bill_type": bill_type,
        "session": session,
        "bill_url": bill_url,
        "fiscal_note_url": fiscal_url,
        "bill_text": bill_text[:3000],
        "fiscal_note_summary": fiscal_note_summary,
        "total_fiscal_impact": total_fiscal_impact,
        "has_fiscal_note": bool(fiscal_text),
        "exists": True,
        "success": True,
        "cache_hit": False,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    print(f"[BACKGROUND JOB] Analysis complete for {formatted_bill}")
    return result