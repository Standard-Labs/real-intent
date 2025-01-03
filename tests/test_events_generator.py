"""Test the UPDATED events generator."""
import pytest
import os
import warnings
from dotenv import load_dotenv
import datetime
import re

# Suppress reportlab deprecation warning
warnings.filterwarnings(
    "ignore",
    message="ast.NameConstant is deprecated",
    category=DeprecationWarning
)

from real_intent.deliver.events.main import (
    Event,
    EventsResponse,
    NoValidJSONError,
    EventsGenerator,
)

# Load environment variables
load_dotenv()


@pytest.fixture
def scrapybara_api_key():
    """Get Scrapybara API key from environment."""
    return os.getenv("SCRAPYBARA_API_KEY")


@pytest.fixture
def anthropic_api_key():
    """Get Anthropic API key from environment."""
    return os.getenv("ANTHROPIC_API_KEY")


@pytest.fixture
def events_generator_90210(scrapybara_api_key, anthropic_api_key):
    """Create an EventsGenerator instance for Beverly Hills."""
    return EventsGenerator("90210", scrapybara_api_key, anthropic_api_key)


@pytest.fixture
def events_generator_22101(scrapybara_api_key, anthropic_api_key):
    """Create an EventsGenerator instance for McLean."""
    return EventsGenerator("22101", scrapybara_api_key, anthropic_api_key)


def extract_date_from_range(date_str: str) -> str:
    """Extract the first date from a date range string."""
    # Try to match YYYY-MM-DD format first
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return date_str
    
    # Try to extract first date from a range (e.g., "2024-12-22 to 2024-12-29")
    match = re.search(r'(\d{4}-\d{2}-\d{2})', date_str)
    if match:
        return match.group(1)
    
    raise ValueError(f"Could not extract date from: {date_str}")


@pytest.mark.skipif(not os.getenv("SCRAPYBARA_API_KEY") or not os.getenv("ANTHROPIC_API_KEY"), reason="Scrapybara or Anthropic API key not found")
def test_beverly_hills_events(events_generator_90210):
    """Test generating events for Beverly Hills (90210)."""
    response = events_generator_90210.generate_events()
    
    # Verify response structure
    assert isinstance(response, EventsResponse)
    assert isinstance(response.events, list)
    assert isinstance(response.summary, str)
    
    # Verify we got some events
    assert len(response.events) >= 3, "Should have at least 3 events"
    
    # Verify each event
    for event in response.events:
        assert event.title, "Event should have a title"
        assert event.date, "Event should have a date"
        assert event.description, "Event should have a description"
        
        # Extract and verify date
        date_str = extract_date_from_range(event.date)
        event_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        # Allow events within the next month
        today = datetime.datetime.now() - datetime.timedelta(days=1)  # 1 day grace period
        month_from_now = today + datetime.timedelta(days=32)  # ~1 month + 1 day grace period
        assert today <= event_date <= month_from_now, f"Event date {event_date} should be within the next month"
        
        # Verify description is meaningful
        assert len(event.description.split()) >= 10, "Description should be meaningful"
    
    # Verify summary
    assert len(response.summary.split()) >= 20, "Summary should be meaningful"
    assert "Beverly Hills" in response.summary, "Summary should mention Beverly Hills"


@pytest.mark.skipif(not os.getenv("SCRAPYBARA_API_KEY") or not os.getenv("ANTHROPIC_API_KEY"), reason="Scrapybara or Anthropic API key not found")
def test_mclean_events(events_generator_22101):
    """Test generating events for McLean (22101)."""
    response = events_generator_22101.generate_events()
    
    # Verify response structure
    assert isinstance(response, EventsResponse)
    assert isinstance(response.events, list)
    assert isinstance(response.summary, str)
    
    # Verify we got some events
    assert len(response.events) >= 3, "Should have at least 3 events"
    
    # Verify each event
    for event in response.events:
        assert event.title, "Event should have a title"
        assert event.date, "Event should have a date"
        assert event.description, "Event should have a description"
        
        # Extract and verify date
        date_str = extract_date_from_range(event.date)
        event_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        # Allow events within the next month
        today = datetime.datetime.now() - datetime.timedelta(days=1)  # 1 day grace period
        month_from_now = today + datetime.timedelta(days=32)  # ~1 month + 1 day grace period
        assert today <= event_date <= month_from_now, f"Event date {event_date} should be within the next month"
        
        # Verify description is meaningful
        assert len(event.description.split()) >= 10, "Description should be meaningful"
    
    # Verify summary
    assert len(response.summary.split()) >= 20, "Summary should be meaningful"
    assert "McLean" in response.summary, "Summary should mention McLean"


@pytest.mark.skipif(not os.getenv("SCRAPYBARA_API_KEY") or not os.getenv("ANTHROPIC_API_KEY"), reason="Scrapybara or Anthropic API key not found")
def test_pdf_generation(events_generator_90210):
    """Test generating PDF from events."""
    # First get some events
    response = events_generator_90210.generate_events()
    
    # Generate PDF
    pdf_buffer = events_generator_90210.generate_pdf_buffer(response)
    
    # Verify PDF was generated
    assert pdf_buffer.getvalue().startswith(b'%PDF'), "Should be a valid PDF"
    assert len(pdf_buffer.getvalue()) > 1000, "PDF should have meaningful content"


@pytest.mark.skipif(not os.getenv("SCRAPYBARA_API_KEY") or not os.getenv("ANTHROPIC_API_KEY"), reason="Scrapybara or Anthropic API key not found")
def test_invalid_zip_code():
    """Test initialization with invalid zip code."""
    scrapybara_api_key = os.getenv("SCRAPYBARA_API_KEY")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    
    # Test non-string zip code
    with pytest.raises(ValueError):
        EventsGenerator(12345, scrapybara_api_key, anthropic_api_key)
    
    # Test empty zip code
    with pytest.raises(ValueError):
        EventsGenerator("", scrapybara_api_key, anthropic_api_key)
    
    # Test wrong length zip code
    with pytest.raises(ValueError):
        EventsGenerator("1234", scrapybara_api_key, anthropic_api_key)
    
    # Test non-numeric zip code
    with pytest.raises(ValueError):
        EventsGenerator("abcde", scrapybara_api_key, anthropic_api_key)


@pytest.mark.skipif(not os.getenv("SCRAPYBARA_API_KEY") or not os.getenv("ANTHROPIC_API_KEY"), reason="Scrapybara or Anthropic API key not found")
def test_invalid_api_key():
    """Test initialization with invalid API key."""
    # Test non-string API key
    with pytest.raises(ValueError):
        EventsGenerator("90210", 12345, 54321)
    
    # Test empty API key
    with pytest.raises(ValueError):
        EventsGenerator("90210", "", "")
    
    # Test None API key
    with pytest.raises(ValueError):
        EventsGenerator("90210", None, None)
