"""Utilities for event generation."""
from scrapybara.core.api_error import ApiError
from anthropic import APIStatusError
from playwright.sync_api import Error as PlaywrightError
from pydantic import ValidationError

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet

import json
from typing import Any, Callable
from io import BytesIO

from real_intent.internal_logging import log
from real_intent.events.errors import NoValidJSONError
from real_intent.events.models import EventsResponse

# --- Temporary ---

class ToolResult:
    """Represents the result of a tool execution."""

    def __init__(self, output: str | None = None, error: str | None = None, 
                 base64_image: str | None = None, system: str | None = None):
        self.output = output
        self.error = error
        self.base64_image = base64_image
        self.system = system


class CLIResult(ToolResult):
    """A ToolResult that can be rendered as a CLI output."""

    def __init__(self, output:str | None = None, error: str | None = None, 
                 base64_image: str | None = None, system: str | None = None):
        super().__init__(output, error, base64_image, system)


class ToolError(Exception):
    """Raised when a tool encounters an error."""
    def __init__(self, message):
        self.message = message



def extract_json_only(response_str: str) -> dict[str, Any]:
    """
    Parse a string response and pull out everything between the first { and last }
    then return it as a dictionary. Allows excess text before and after valid JSON
    without causing an error.
    """
    start_index = response_str.find("{")
    end_index = response_str.rfind("}")

    if start_index == -1 or end_index == -1:
        raise NoValidJSONError(response_str)

    return json.loads(response_str[start_index:end_index+1])


def extract_json_array(response: str):
    """
    Parse a string response and pull out everything between the first [ and last ]
    then return it as a list. Allows excess text before and after valid JSON array
    without causing an error.
    """
    start_index = response.find("[")
    end_index = response.rfind("]")

    if start_index == -1 or end_index == -1:
        raise NoValidJSONError("Array not found in response")

    return json.loads(response[start_index:end_index + 1])


def retry_generation(func: Callable):
    """Retry the generation once if it fails validation."""
    MAX_ATTEMPTS: int = 2

    def wrapper(*args, **kwargs):
        """Run the function, catch error, then retry once if exception occurs."""
        for attempt in range(1, MAX_ATTEMPTS+1):
            try:
                return func(*args, **kwargs)
            except (ValidationError, KeyError, NoValidJSONError, json.decoder.JSONDecodeError, ApiError, APIStatusError, PlaywrightError, ToolError) as err:
                if attempt < MAX_ATTEMPTS:  # Log warning for first n-1 attempts
                    log("warn", f"Function {func.__name__} failed validation, attempt {attempt} of {MAX_ATTEMPTS}.")
                else:  # Log error for the last attempt
                    log(
                        "error", 
                        f"Function {func.__name__} failed validation after {MAX_ATTEMPTS} attempts.",
                        exc_info=err
                    )
        
        # If we've exhausted all attempts, raise the last exception
        raise

    return wrapper


# ---- PDF ----

def generate_pdf_buffer(events_response: EventsResponse) -> BytesIO:
    """
    Generate a PDF file with the events and summary.
    """
    output_buffer = BytesIO()
    c = canvas.Canvas(output_buffer, pagesize=letter)
    width, height = letter

    # background color
    c.setFillColor(colors.aliceblue)
    c.rect(0, 0, width, height, fill=1)  

    title = "Upcoming Local Events"
    title_font_size = 16

    text_width = c.stringWidth(title, "Helvetica-Bold", title_font_size)
    x_position = (width - text_width) / 2  

    # Title
    c.setFillColor(colors.red)
    c.rect(0, height - 50, width, 50, fill=1) 
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", title_font_size)
    c.drawString(x_position, height - 30, title)

    styles = getSampleStyleSheet()
    normal_style = styles['Normal']
    normal_style.fontName = 'Helvetica'
    normal_style.fontSize = 10
    normal_style.leading = 12

    # Summary
    summary_paragraph = Paragraph(events_response.summary, normal_style)
    paragraph_width = width - 200
    summary_height = summary_paragraph.getSpaceBefore() + summary_paragraph.getSpaceAfter() + summary_paragraph.wrap(paragraph_width, 100)[1]
    summary_paragraph.drawOn(c, 100, height - 60 - summary_height)
    y_position = height - 60 - summary_height - 20

    normal_style = styles['Normal']
    normal_style.fontName = 'Helvetica'
    normal_style.fontSize = 10
    normal_style.leading = 12

    bottom_margin = 70

    for idx, event in enumerate(events_response.events):
        if y_position < bottom_margin:
            log("warning", f"Not all events could fit on the PDF. Truncated at event {idx+1}")
            break

        c.setFillColor(colors.red) 
        c.setFont("Helvetica-Bold", 14)
        c.drawString(100, y_position, event.truncated_title)
        y_position -= 20

        c.setFillColor(colors.green) 
        c.setFont("Helvetica", 12)
        c.drawString(100, y_position, f"Date: {event.date}")
        y_position -= 20

        paragraph = Paragraph(event.description, normal_style)
        paragraph_width = width - 200
        paragraph_height = paragraph.getSpaceBefore() + paragraph.getSpaceAfter() + paragraph.wrap(paragraph_width, 100)[1]
        paragraph.drawOn(c, 100, y_position - paragraph_height)
        y_position -= paragraph_height + 20

        c.setFont("Helvetica-Oblique", 10)
        c.setFillColor(colors.blue)
        c.drawString(100, y_position, f"Link: {event.link[:70] + '...' if event.link and len(event.link) > 70 else event.link if event.link else 'N/A'}")
        c.linkURL(event.link, (100, y_position, width - 100, y_position + 10)) if event.link else None
        y_position -= 20

        c.setFillColor(colors.black) 

        c.setStrokeColor(colors.gold)
        c.setLineWidth(1)
        c.line(100, y_position, width - 100, y_position)
        y_position -= 20 

    c.save()

    output_buffer.seek(0)
    return output_buffer
