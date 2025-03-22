"""Common error classes for event generation."""


class NoValidJSONError(ValueError):
    """Exception raised when no valid JSON is found in the response."""

    def __init__(self, content: str):
        super().__init__(content)


class NoEventsFoundError(Exception):
    """Exception raised when no events are found for a zip code."""

    def __init__(self, zip_code: str):
        super().__init__(f"No events found for zip code {zip_code}")


class NoLinksFoundError(Exception):
    """Exception raised when no links are found in the response."""

    def __init__(self, query: str):
        super().__init__(f"No links for query: {query}")
       
        
class BatchNotCompleteError(Exception):
    """Exception raised when a batch of events is not complete."""

    def __init__(self, batch_id: str):
        super().__init__(f"Batch with ID {batch_id} is not complete.")