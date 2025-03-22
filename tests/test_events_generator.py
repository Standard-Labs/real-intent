"""Test the event generators (Scrapybara and Perplexity)."""
import pytest
from dotenv import load_dotenv

import os
import re
import warnings
import datetime

from real_intent.events import (
    Event,
    EventsResponse,
    PerplexityEventsGenerator,
    ScrapybaraEventsGenerator,
    SerpEventsGenerator
)
from real_intent.events.errors import NoEventsFoundError

# Suppress reportlab deprecation warning
warnings.filterwarnings(
    "ignore",
    message="ast.NameConstant is deprecated",
    category=DeprecationWarning
)

# Load environment variables
load_dotenv()


@pytest.fixture
def scrapybara_events_generator():
    """Create a ScrapybaraEventsGenerator instance."""
    scrapybara_api_key = os.getenv("SCRAPYBARA_API_KEY")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    
    if not scrapybara_api_key or not anthropic_api_key:
        pytest.skip("Scrapybara and Anthropic API keys required")
    
    return ScrapybaraEventsGenerator(
        scrapybara_api_key,
        anthropic_api_key
    )


@pytest.fixture
def perplexity_events_generator():
    """Create a PerplexityEventsGenerator instance."""
    perplexity_api_key = os.getenv("PERPLEXITY_API_KEY")
    
    if not perplexity_api_key:
        pytest.skip("Perplexity API key not found")
    
    return PerplexityEventsGenerator(
        perplexity_api_key
    )


@pytest.fixture
def serp_events_generator():
    """Create a SerpEventsGenerator instance."""
    serp_api_key = os.getenv("SERP_API_KEY")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    geo_api_key = os.getenv("GEO_API_KEY")
    
    if not serp_api_key or not anthropic_api_key:
        pytest.skip("Serp and Anthropic keys required")
    
    return SerpEventsGenerator(
        serp_api_key,
        anthropic_api_key,
        start_date=None,
        end_date=None,
        geo_key=geo_api_key
    )


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


def test_beverly_hills_events_scrapybara(scrapybara_events_generator):
    """Test generating events for Beverly Hills (90210) using Scrapybara."""
    response = scrapybara_events_generator.generate("90210")
    
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
        today = (datetime.datetime.now() - datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)  # 1 day grace period
        month_from_now = today + datetime.timedelta(days=32)  # ~1 month + 1 day grace period
        assert today <= event_date <= month_from_now, f"Event date {event_date} should be within the next month"
        
        # Verify description is meaningful
        assert len(event.description.split()) >= 10, "Description should be meaningful"
    
    # Verify summary
    assert len(response.summary.split()) >= 20, "Summary should be meaningful"
    assert "Beverly Hills" in response.summary, "Summary should mention Beverly Hills"


def test_lawrenceville_ga_events_serp(serp_events_generator):
    """Test generating events for Lawrenceville, GA (30043) using Olostep's SERP API."""
    response = serp_events_generator.generate("30043")
    
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
        today = (datetime.datetime.now() - datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)  # 1 day grace period
        month_from_now = today + datetime.timedelta(days=32)  # ~1 month + 1 day grace period
        assert today <= event_date <= month_from_now, f"Event date {event_date} should be within the next month"
        
        # Verify description is meaningful
        assert len(event.description.split()) >= 10, "Description should be meaningful"
    
    # Verify summary
    assert len(response.summary.split()) >= 20, "Summary should be meaningful"
    assert "Lawrenceville" in response.summary, "Summary should mention Lawrenceville"


@pytest.fixture
def dummy_events_response():
    """Create a dummy EventsResponse for testing."""
    return EventsResponse(
        events=[
            Event(
                title="Test Event 1",
                date="2024-03-15",
                description="A fun test event happening in Beverly Hills",
                link="https://example.com/event1"
            ),
            Event(
                title="Test Event 2",
                date="2024-03-20",
                description="Another exciting event in the 90210 area",
                link="https://example.com/event2"
            ),
            Event(
                title="Test Event 3",
                date="2024-03-25",
                description="A third amazing event for testing purposes",
                link="https://example.com/event3"
            )
        ],
        summary="A collection of upcoming events in Beverly Hills featuring entertainment, culture, and community gatherings."
    )


def test_pdf_generation(scrapybara_events_generator, dummy_events_response):
    """Test generating PDF from events using Scrapybara."""
    # Generate PDF using dummy data
    pdf_buffer = scrapybara_events_generator.to_pdf_buffer(dummy_events_response)
    
    # Verify PDF was generated
    assert pdf_buffer.getvalue().startswith(b'%PDF'), "Should be a valid PDF"
    assert len(pdf_buffer.getvalue()) > 1000, "PDF should have meaningful content"


def test_invalid_zip_code_scrapybara(scrapybara_events_generator):
    """Test generation with invalid zip code for Scrapybara."""
    # Test non-string zip code
    with pytest.raises(ValueError):
        scrapybara_events_generator.generate(12345)
    
    # Test empty zip code
    with pytest.raises(ValueError):
        scrapybara_events_generator.generate("")
    
    # Test wrong length zip code
    with pytest.raises(ValueError):
        scrapybara_events_generator.generate("1234")
    
    # Test non-numeric zip code
    with pytest.raises(ValueError):
        scrapybara_events_generator.generate("abcde")


def test_invalid_api_key_scrapybara():
    """Test initialization with invalid API key for Scrapybara."""
    # Test non-string API key
    with pytest.raises(ValueError):
        ScrapybaraEventsGenerator(12345, 54321)
    
    # Test empty API key
    with pytest.raises(ValueError):
        ScrapybaraEventsGenerator("", "")
    
    # Test None API key
    with pytest.raises(ValueError):
        ScrapybaraEventsGenerator(None, None)


@pytest.mark.skip(reason="Perplexity unreliable and not in use")
def test_chicago_events_perplexity(perplexity_events_generator):
    """Test generating events for Chicago (60629) using Perplexity."""
    try:
        response = perplexity_events_generator.generate("60629")
    except NoEventsFoundError:
        pytest.skip("No events found for this zip code.")
    
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
        today = (datetime.datetime.now() - datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)  # 1 day grace period
        month_from_now = today + datetime.timedelta(days=32)  # ~1 month + 1 day grace period
        assert today <= event_date <= month_from_now, f"Event date {event_date} should be within the next month"
        
        # Verify description is meaningful
        assert len(event.description.split()) >= 10, "Description should be meaningful (at least 10 words)"
    
    # Verify summary
    assert len(response.summary.split()) >= 20, "Summary should be meaningful (at least 20 words)"


@pytest.mark.skip(reason="Perplexity unreliable and not in use")
def test_invalid_zip_code_perplexity(perplexity_events_generator):
    """Test generation with invalid zip code for Perplexity."""
    # Test non-string zip code
    with pytest.raises(ValueError):
        perplexity_events_generator.generate(12345)
    
    # Test empty zip code
    with pytest.raises(ValueError):
        perplexity_events_generator.generate("")
    
    # Test wrong length zip code
    with pytest.raises(ValueError):
        perplexity_events_generator.generate("1234")
    
    # Test non-numeric zip code
    with pytest.raises(ValueError):
        perplexity_events_generator.generate("abcde")


@pytest.mark.skip(reason="Perplexity unreliable and not in use")
def test_invalid_api_key_perplexity():
    """Test initialization with invalid API key for Perplexity."""
    # Test non-string API key
    with pytest.raises(ValueError):
        PerplexityEventsGenerator(12345)
    
    # Test empty API key
    with pytest.raises(ValueError):
        PerplexityEventsGenerator("")
    
    # Test None API key
    with pytest.raises(ValueError):
        PerplexityEventsGenerator(None)
