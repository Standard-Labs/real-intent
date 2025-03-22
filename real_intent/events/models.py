"""Event models."""
from pydantic import BaseModel
import string


class Event(BaseModel):
    """Event object."""
    title: str
    date: str
    description: str
    link: str | None = None
    
    @property
    def truncated_title(self) -> str:
        """Truncate the title to a maximum length."""
        if len(self.title) > 70:
            return string.capwords(self.title[:70] + "...")

        return string.capwords(self.title)


class EventsResponse(BaseModel):
    """Response object, containing events and summary."""
    events: list[Event]
    summary: str
    
    
class OrganicLink(BaseModel):
    """Model for organic links."""
    title: str | None = None
    link: str | None = None
    snippet: str | None = None
