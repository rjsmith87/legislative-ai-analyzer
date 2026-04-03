"""Tests for the Texas Bill Analyzer Flask API."""
import json
import pytest
from unittest.mock import patch, MagicMock
import app


@pytest.fixture
def client():
    """Create a Flask test client."""
    app.app.testing = True
    with app.app.test_client() as client:
        yield client


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        """GET /health should return 200 with ok=True and version info."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data["ok"] is True
        assert data["service"] == "Texas Bill Analyzer"
        assert "version" in data
        assert "endpoints" in data

    def test_health_reports_feature_flags(self, client):
        """Health endpoint should include feature availability flags."""
        response = client.get("/health")
        data = response.get_json()
        assert "features" in data
        assert "ai_enabled" in data["features"]
        assert "redis_caching" in data["features"]


class TestAnalyzeBillValidation:
    def test_missing_bill_number_returns_400(self, client):
        """POST /analyzeBill without bill_number should return 400."""
        response = client.post(
            "/analyzeBill",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert data["error_code"] == "MISSING_BILL_NUMBER"

    def test_invalid_bill_format_returns_400(self, client):
        """POST /analyzeBill with an invalid bill format should return 400."""
        response = client.post(
            "/analyzeBill",
            data=json.dumps({"bill_number": "INVALID"}),
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["error_code"] == "INVALID_BILL_FORMAT"

    def test_agentforce_missing_bill_number_returns_400(self, client):
        """POST /analyzeBillForAgentforce without bill_number should return 400."""
        response = client.post(
            "/analyzeBillForAgentforce",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False


class TestParseBillNumber:
    def test_house_bill(self):
        """HB 1 should parse to ('HB', '00001')."""
        bill_type, bill_num = app.parse_bill_number("HB 1")
        assert bill_type == "HB"
        assert bill_num == "00001"

    def test_senate_bill(self):
        """SB 23 should parse to ('SB', '00023')."""
        bill_type, bill_num = app.parse_bill_number("SB 23")
        assert bill_type == "SB"
        assert bill_num == "00023"

    def test_house_joint_resolution(self):
        """HJ 100 should parse correctly."""
        bill_type, bill_num = app.parse_bill_number("HJ 100")
        assert bill_type == "HJ"
        assert bill_num == "00100"

    def test_no_space(self):
        """HB150 (no space) should still parse."""
        bill_type, bill_num = app.parse_bill_number("HB150")
        assert bill_type == "HB"
        assert bill_num == "00150"

    def test_lowercase(self):
        """hb 1 (lowercase) should parse correctly."""
        bill_type, bill_num = app.parse_bill_number("hb 1")
        assert bill_type == "HB"
        assert bill_num == "00001"

    def test_invalid_returns_none(self):
        """Invalid input should return (None, None)."""
        bill_type, bill_num = app.parse_bill_number("INVALID")
        assert bill_type is None
        assert bill_num is None

    def test_empty_string(self):
        """Empty string should return (None, None)."""
        bill_type, bill_num = app.parse_bill_number("")
        assert bill_type is None
        assert bill_num is None


class TestGetAppropriateTextLimit:
    def test_short_text(self):
        """Short text (<50k) should return min(length, 10000)."""
        assert app.get_appropriate_text_limit("x" * 5000) == 5000
        assert app.get_appropriate_text_limit("x" * 10000) == 10000
        assert app.get_appropriate_text_limit("x" * 30000) == 10000

    def test_medium_text(self):
        """Medium text (50k-100k) should return 8000."""
        assert app.get_appropriate_text_limit("x" * 60000) == 8000

    def test_large_text(self):
        """Large text (100k-150k) should return 6000."""
        assert app.get_appropriate_text_limit("x" * 120000) == 6000

    def test_huge_text(self):
        """Very large text (>150k) should return 4000."""
        assert app.get_appropriate_text_limit("x" * 200000) == 4000


class TestCacheKeyGeneration:
    def test_normalizes_bill_number(self):
        """Cache key should normalize bill numbers consistently."""
        key1 = app.get_cache_key("HB 1", "89R")
        key2 = app.get_cache_key("HB1", "89R")
        key3 = app.get_cache_key("hb 1", "89R")
        assert key1 == key2 == key3
        assert key1 == "bill_analysis:89R:HB00001"

    def test_different_bills_different_keys(self):
        """Different bills should produce different cache keys."""
        key1 = app.get_cache_key("HB 1", "89R")
        key2 = app.get_cache_key("SB 1", "89R")
        assert key1 != key2

    def test_different_sessions_different_keys(self):
        """Same bill in different sessions should produce different keys."""
        key1 = app.get_cache_key("HB 1", "89R")
        key2 = app.get_cache_key("HB 1", "88R")
        assert key1 != key2


class TestShouldFetchFiscalNote:
    def test_returns_true_for_fiscal_keywords(self):
        """Bills mentioning fiscal terms should trigger fiscal note fetch."""
        assert app.should_fetch_fiscal_note("This bill requires an appropriation of funds") is True
        assert app.should_fetch_fiscal_note("The estimated cost is $5 million") is True
        assert app.should_fetch_fiscal_note("Budget allocation for the department") is True

    def test_returns_false_for_non_fiscal_text(self):
        """Bills without fiscal keywords should not trigger fiscal note fetch."""
        assert app.should_fetch_fiscal_note("This bill renames a highway") is False
        assert app.should_fetch_fiscal_note("Designates an official state symbol") is False

    def test_case_insensitive(self):
        """Keyword matching should be case-insensitive."""
        assert app.should_fetch_fiscal_note("APPROPRIATION required") is True
        assert app.should_fetch_fiscal_note("Total REVENUE impact") is True


class TestFormatCompleteResponse:
    def test_includes_fiscal_note(self):
        """Response with fiscal data should include impact string."""
        result = app.format_complete_response(
            "HB00150", "Test summary", "Fiscal summary text", -5000000.0, "http://example.com"
        )
        assert "HB00150" in result
        assert "Test summary" in result
        assert "Fiscal summary text" in result
        assert "-$5.00 million" in result

    def test_no_fiscal_note(self):
        """Response without fiscal data should indicate none available."""
        result = app.format_complete_response(
            "HB00150", "Test summary", "", 0, "No fiscal note available"
        )
        assert "No fiscal analysis is currently available" in result

    def test_positive_impact_formatting(self):
        """Positive fiscal impacts should show with + sign."""
        result = app.format_complete_response(
            "SB00001", "Summary", "Revenue note", 2000000000.0, "http://example.com"
        )
        assert "+$2.00 billion" in result
