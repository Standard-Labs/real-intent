"""Event generation."""
from real_intent.events.models import Event, EventsResponse
from real_intent.events.perplexity import PerplexityEventsGenerator
from real_intent.events.scrapy_claude import ScrapybaraEventsGenerator
from real_intent.events.serp import SerpEventsGenerator
