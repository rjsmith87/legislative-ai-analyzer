# tasks.py - Background tasks for analyzing huge bills
from datetime import datetime

from utils import (
    CURRENT_SESSION,
    _telicon_request,
    extract_text_from_pdf_bytes,
    extract_fiscal_data_with_claude,
    parse_bill_number,
    try_bill_url_patterns,
    try_fiscal_note_patterns,
    should_fetch_fiscal_note,
)


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
                        # Use longer timeout for background jobs
                        fiscal_data = extract_fiscal_data_with_claude(fiscal_text, timeout=120)
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
