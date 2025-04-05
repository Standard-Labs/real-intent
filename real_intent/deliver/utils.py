"""Shared utilities for CRM deliverers."""
import requests
import time
import random
from functools import wraps
from enum import StrEnum

from real_intent.internal_logging import log


# ---- Models ----

class EventType(StrEnum):
    """Event types for adding a lead."""
    REGISTRATION = "Registration"
    INQUIRY = "Inquiry"
    SELLER_INQUIRY = "Seller Inquiry"
    PROPERTY_INQUIRY = "Property Inquiry"
    GENERAL_INQUIRY = "General Inquiry"
    VIEWED_PROPERTY = "Viewed Property"
    SAVED_PROPERTY = "Saved Property"
    VISITED_WEBSITE = "Visited Website"
    INCOMING_CALL = "Incoming Call"
    UNSUBSCRIBED = "Unsubscribed"
    PROPERTY_SEARCH = "Property Search"
    SAVED_PROPERTY_SEARCH = "Saved Property Search"
    VISITED_OPEN_HOUSE = "Visited Open House"
    VIEWED_PAGE = "Viewed Page"


# ---- Parameterized Exceptions ----

class InvalidCRMCredentialsError(Exception):
    """Raised when invalid API credentials are provided."""
    def __init__(self, crm_name: str, message: str = None):
        self.crm_name = crm_name
        self.message = message or f"Invalid API credentials provided for {crm_name}."
        super().__init__(self.message)


class CRMAccountInactiveError(Exception):
    """Raised when the CRM account is inactive."""
    def __init__(self, crm_name: str, message: str = None):
        self.crm_name = crm_name
        self.message = message or f"{crm_name} account is inactive."
        super().__init__(self.message)


# ---- Rate Limiting Decorator Function ----

def rate_limited(crm: str | None = None):
    """
    Decorator to handle rate limiting for CRM API calls.
    
    Args:
        crm (str | None): The name of the CRM for logging purposes.
    """
    def decorator(func: callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for _ in range(10):
                try:
                    return func(*args, **kwargs)
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 429:  # Too Many Requests
                        retry_after = int(e.response.headers.get('Retry-After', 10))
                        sleep_delay: float = retry_after + (random.randint(50, 100) / 100)
                        log("warn", f"Rate limit hit for {crm}. Retrying in {sleep_delay} seconds.")
                        time.sleep(sleep_delay)
                    else:
                        raise
            raise Exception(f"Max retries (10) exceeded due to rate limiting for {crm}.")
        return wrapper
    return decorator
