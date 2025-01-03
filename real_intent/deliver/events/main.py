import datetime
import json
from typing import Any, Callable, cast
from anthropic import Anthropic
from anthropic.types.beta import (
    BetaToolResultBlockParam,
    BetaMessageParam,
)
from pydantic import BaseModel, ValidationError
from scrapybara import Scrapybara
from playwright.sync_api import sync_playwright

from real_intent.deliver.events.utils import _make_api_tool_result, ToolCollection, SearchTool, ToolCollection, ComputerTool
from scrapybara.anthropic.base import ToolError
from scrapybara.client import Instance

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO

from real_intent.internal_logging import log, log_span


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
            return self.title[:70] + "..."

        return self.title


class EventsResponse(BaseModel):
    """Response object, containing events and summary."""
    events: list[Event]
    summary: str


class NoValidJSONError(ValueError):
    """Exception raised when no valid JSON is found in the response."""

    def __init__(self, content: str):
        super().__init__(content)


class NoEventsFoundError(Exception):
    """Exception raised when no events are found for a zip code."""

    def __init__(self, zip_code: str):
        super().__init__(f"No events found for zip code {zip_code}")


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
        start_index = response.find("[")
        end_index = response.rfind("]")

        if start_index == -1 or end_index == -1:
            raise NoValidJSONError("Array not found in response") # temporary

        return json.loads(response[start_index:end_index + 1])


def retry_generation(func: Callable):
    """Retry the generation four times if it fails validation."""
    MAX_ATTEMPTS: int = 4

    def wrapper(*args, **kwargs):
        """Run the function, catch error, then retry up to four times."""
        for attempt in range(1, MAX_ATTEMPTS+1):
            try:
                return func(*args, **kwargs)
            except (ValidationError, KeyError, NoValidJSONError, json.decoder.JSONDecodeError, ToolError, NoEventsFoundError):
                if attempt < MAX_ATTEMPTS:  # print warning for first n-1 attempts
                    log("warn", f"Function {func.__name__} failed validation, attempt {attempt} of {MAX_ATTEMPTS}.")
                else:  # print error for the last attempt
                    log("error", f"Function {func.__name__} failed validation after {MAX_ATTEMPTS} attempts.")
        
        # If we've exhausted all attempts, raise the last exception
        raise

    return wrapper


class EventsGenerator:


    def __init__(self, zip_code: str, scrapybara_key: str, anthropic_key: str, instance_type: str = "small"):
        if not isinstance(zip_code, str) or not zip_code.isnumeric() or len(zip_code) != 5:
            raise ValueError("Invalid ZIP code. ZIP code must be a 5-digit numeric string.")
        
        if not isinstance(scrapybara_key, str) or not scrapybara_key:
            raise ValueError("Invalid Scrapybara API key. Please provide a valid API key.")
        
        if not isinstance(anthropic_key, str) or not anthropic_key:
            raise ValueError("Invalid Anthropic API key. Please provide a valid API key.")


        self.scrapybara_client = Scrapybara(api_key=scrapybara_key)
        self.anthropic_client = Anthropic(api_key=anthropic_key)
    
        self.zip_code = zip_code
        self.start_date = datetime.datetime.now().strftime("%B %d, %Y")
        self.end_date = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime("%B %d, %Y")

        self.instance_type = instance_type

        # initialized only when needed in run()
        self.instance = None
        self.tools = None


    def initialize_instance(self) -> None:
        """ Intialize the Scrapybara instance and tools. """
        self.instance = self.scrapybara_client.start(instance_type=self.instance_type)
        self.tools: ToolCollection = ToolCollection(
            ComputerTool(),
            SearchTool()
        )
        self.tools.set_instance(self.instance)


    def prompt(self) -> tuple[str, str]:
        return f"""
            <SYSTEM_CAPABILITY>
            * You are utilising an Ubuntu virtual machine using linux architecture with internet access.
            * You can feel free to install Ubuntu applications with your bash tool. Use curl instead of wget.
            * Using bash tool you can start GUI applications, but you need to set export DISPLAY=:1 and use a subshell. For example "(DISPLAY=:1 xterm &)". GUI apps run with bash tool will appear within your desktop environment, but they may take some time to appear. Take a screenshot to confirm it did.
            * When using your bash tool with commands that are expected to output very large quantities of text, redirect into a tmp file and use str_replace_editor or `grep -n -B <lines before> -A <lines after> <query> <filename>` to confirm output.
            * When viewing a page it can be helpful to zoom out so that you can see everything on the page. Either that, or make sure you scroll down to see everything before deciding something isn't available.
            * When using your computer function calls, they take a while to run and send back to you. Where possible/feasible, try to chain multiple of these calls all into one function calls request.
            * The current date is {self.start_date}.
            </SYSTEM_CAPABILITY>

            <YOUR_USECASE>
            User provides you not only with natural language prompt, but also an output schema of jsonschema format.
            This schema is derived from Pydantic model user has submitted to the system, and user intends to receive filled pydantic object.
            Your role is to respond when you are done EXCLUSIVELY with a JSON object which should fit the schema. Do not write usual response like in a chat.
            Essentially, you are a smart information retriever. After your JSON object answer is received, a Pydantic model will be instantiated based on it and returned to user.
            Never respond with common text. Always respond with a valid JSON object, according to user's instructions and schema.

            Note: The schema represents ONE object, you will provide a list of these objects, as in surrond multiple objects with square brackets.
            </YOUR_USECASE>

            <JSON_SCHEMA>
            {json.dumps(Event.model_json_schema())}
            Note: The schema represents ONE object, you will provide a list of these objects.
            Note: The data attribute represents the date or date range of the event in ISO 8601 format (YYYY-MM-DD). Make sure to follow this format when providing the date.
            </JSON_SCHEMA>

            <IMPORTANT>
            * When using Chrome, if a startup wizard appears, IGNORE IT. Do not even click "skip this step". Instead, click on the address bar where it says "Search or enter address", and enter the appropriate search term or URL there.
            * If the item you are looking at is a pdf, if after taking a single screenshot of the pdf it seems that you want to read the entire document instead of trying to continue to read the pdf from your screenshots + navigation, determine the URL, use curl to download the pdf, install and use pdftotext to convert it to a text file, and then read that text file directly with your StrReplaceEditTool.
            * If you are at the beginning of the conversation and take a screenshot, the screen may show up black. In this case just move the mouse to the center of the screen and do a left click. Then screenshot again.
            * If something is not working for second time, stop trying, make final message without tool calls and ask user for help.
            * Sometimes you start at ALREADY open page. If you want to search something, make sure you use GOOGLE OR CHROME SEARCH BAR, not the website one if it has one. Do not get confused!
            * Please do not try to login or try to get access to information behind login page, it is still in development.
            * If you are interrupted by stupid popups close them as fast as possible, do not try to refresh the page or wait.
            </IMPORTANT>

            Guidelines:
            - Launch GUI apps using bash with DISPLAY=:1 
            - Take screenshots to verify your actions
            - Look for compelling reasons to engage
            - When you are done, submit a final message to user with the JSON response fitting the schema of the provided json schema.
            - In your final answer never write anything beyond of {{}} JSON object, never, NOBODY WILL READ ANYTHING BEYOND JSON.
            - Utilize the 'search' tool to make ANY searches in the browser, do not attempt to type in the search bar.
            - After you utilize the 'search' tool, inspect the page to find the information requested, do not just attemp to search again right away without thoroughly inspecting the page.
            
            <ATTENTION>
            IN YOUR LAST MESSAGE TO USER, FINAL RESPONSE, YOU MUST RESPOND EXCLUSIVELY WITH JSON SCHEMA WITHOUT SURROUNDING CONTENT OUTSIDE OF JSON SCHEMA, MANDATORY
            DO NOT INDENT RESPONSE STRING, no \n or whatever, just {{}} string.

            YOU MUST NEVER, EVER, EVER WRITE NATURAL RESPONSE TEXT IN YOUR FINAL MESSAGE TO USER (the one without subsequent tool calls) OUTSIDE OF JSON {{}} OBJECT, NOBODY READS STUFF OUTSIDE JSON OBJECT, OBEY THE SCHEMA NO MATTER WHAT!
            </ATTENTION>

        """, f""" 
            Task:
            1. Retrieve events happening in the city with ZIP code: {self.zip_code} within the next 7 days, from {self.start_date} to {self.end_date}. First, find the city corresponding to ZIP code {self.zip_code} to ensure events are within the correct area.
            2. Focus on public events, community activities, festivals, and major holidays during this period (e.g., Christmas, New Year) if there are any.
            3. Include 3–5 unique events relevant to the specified ZIP code and timeframe. Include more if there are many events available that meet the criteria. 
            4. Exclude repeated or duplicate events.

            Requirements:
            - Perform TWO distinct searches:
            - First, search for events based on the city name derived from ZIP code {self.zip_code}. Find the events within the zip code area and timeframe, and if and only if this criteria is met, you will add that event to the list.
            - If the first search yields no results or not enough results, PERFORM a NEW SEARCH and refine your query and adjust search terms and perform a second search. Once again, only add events that meet the criteria.
            - If no results are found after two searches, stop searching and respond with an empty JSON list([]).
            - It is acceptable to return an empty list if there are no events matching the criteria. Avoid fabricated results or predictions of events. All your events must be real and verifiable.
            - Provide a JSON list of events matching the schema. You must include the link. If for some reason there is no link, set that attribute as null.
            - Ensure events are relevant to the area {self.zip_code} and date range {self.start_date} to {self.end_date}.

            Instructions:
            1. Start by finding the city corresponding to the ZIP code {self.zip_code}.
            2. Perform the first search for public events, community activities, festivals, or major holidays in the city and timeframe.
            3. If the first search returns no results, refine or adjust the query and perform a second search.
            4. If the second search also yields no results, return an empty JSON list ([]).

            Final Output:
            - Submit a list of the JSON objects conforming to the provided schema. Do NOT provide any additional information or text outside of the JSON object.
            """


    def summary_prompt(self, events: list[Event]) -> tuple[str, str]:
        """
        Generate the prompt for the summary generation task.
        """
        system = f"""
            You will be helping the user generate a comprehensive summary of a specific zipcode, including details about 
            local events and general conditions. You will be given a list of events happening in the specified zipcode 
            and date range. Your task is to summarize the events in a concise and informative manner, highlighting the 
            key details and providing a general overview of the local community during that period. The summary should also include 
            weather conditions and any other relevant local insights. Your response should be structured in valid JSON format, 
            adhering strictly to the user's instructions.
            """

        user = f"""
            Summarize the events happening in {self.zip_code} between {self.start_date} and {self.end_date} provided to you here.
            \n{events}\n
            Your summary should be informative and engaging, providing a brief overview of the events, the local community,
            and any other relevant details such as weather conditions. Provide a maximum of 5 sentences! 
            
            You must only include the key events and highlights from the list provided. Do not include any additional events.
            
            It should be structured in valid JSON format with one top level key called "summary" that contains a string
            summarizing the events and the local community during the specified period with a maximum of 5 sentences. 
            The summary should be a detailed paragraph that provides an overview of the expected weather conditions for the week, {self.start_date} to {self.end_date},
            and highlights the key events happening in {self.zip_code} from the list provided. Include any relevant insights about the local community, 
            such as cultural aspects, holiday-specific activities, or any notable attractions during this period.
            If there are any major holidays (e.g., Christmas, New Year's), mention how the local events and community activities reflect these.
        """

        return system, user


    def go_to_page(self, instance: Instance, url: str) -> None:  
        cdp_url = instance.browser.start().cdp_url
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(cdp_url)
            page = browser.new_page()
            page.goto(url)
            page.wait_for_load_state("load")


    def _response_to_params(self, response):
        res = []
        for block in response.content:
            if block.type == "text":
                res.append({"type": "text", "text": block.text})
            else:
                res.append(block.model_dump())
        return res
    

    def run(self) -> dict[str, str]:
        try:
            self.initialize_instance()
            
            self.go_to_page(self.instance, "https://www.google.com")  # initial starting point, its faster to start from here, rather then have it come up with the idea to open applications, go to chrome, etc...
            system, user = self.prompt()

            messages: list[BetaMessageParam] = []

            # Add initial command to messages
            messages.append({
            "role": "user",
            "content": [{"type": "text", "text": user}],
            })

            while True:
                # Get Claude's response
                response = self.anthropic_client.beta.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=4096,
                    messages=messages,
                    system=[{"type": "text", "text": system}],
                    tools=self.tools.to_params(),
                    betas=["computer-use-2024-10-22"]
                )

                # Convert response to params
                response_params = self._response_to_params(response)

                # Process response content and handle tools before adding to messages
                tool_result_content: list[BetaToolResultBlockParam] = []

                for content_block in response_params:
                    if content_block["type"] == "text":
                        pass
                        # print(f"\nAssistant: {content_block['text']}")

                    elif content_block["type"] == "tool_use":
                        # print(f"\nTool Use: {content_block['name']}")
                        # print(f"Input: {content_block['input']}")
                    
                        # Execute the tool
                        result = self.tools.run(
                            name=content_block["name"],
                            tool_input=cast(dict[str, Any], content_block["input"])
                        )            

                        if result:
                            tool_result = _make_api_tool_result(result, content_block["id"])

                            if result.output:
                                # print(f"\nTool Output: {result.output}")
                                pass
                            if result.error:
                                # print(f"\nTool Error: {result.error}")
                                pass
                            tool_result_content.append(tool_result)


                # Add assistant's response to messages
                messages.append({
                    "role": "assistant",
                    "content": response_params,
                })

                # If tools were used, add their results to messages
                if tool_result_content:
                    messages.append({
                        "role": "user",
                        "content": tool_result_content
                    })
                else:
                    # No tools used, task is complete
                    self.instance.stop()
                    log("info", f"Sampling loop completed. Last response received: {content_block['text']} ")
                    return content_block['text']        
        except Exception as e:
            self.instance.stop()
            raise()
    

    @retry_generation
    def _generate_events(self) -> EventsResponse:
        """
        Generate a list of events for the specified ZIP code and date range.
        """
       
        response = self.run()
        response = extract_json_array(response)
        events = [Event(title=event['title'], date=event['date'], description=event['description'], link=event['link']) for event in response]
        log("info", f"Generated {len(events)} for {self.zip_code} between {self.start_date} and {self.end_date}")

        if not events:
            raise NoEventsFoundError(self.zip_code)
        
        summary = self.generate_summary(events)
        summary_dict = extract_json_only(summary)

        log("debug", f"Events and summary generated successfully. Events: {events}, Summary: {summary_dict['summary']}")
        return EventsResponse(events=events, summary=summary_dict['summary'])


    def generate_summary(self, events: list[Event]) -> str:

        system, user = self.summary_prompt(events=events)        
        
        try:
            response = self.anthropic_client.completions.create(
            model="claude-2.1",  
            prompt=system + "\n\nHuman:" + user + "\n\nAssistant:", 
            max_tokens_to_sample=500,
            temperature=0.5,
        )

            
            return response.completion

        except Exception as e:
            raise Exception(f"Failed to generate summary: {e}")
   

    def generate_events(self) -> EventsResponse:
        """print spanned generation of events for a given zip code."""
        with log_span(f"Generating events for {self.zip_code}", _level="debug"):
            return self._generate_events()


    def generate_pdf_buffer(self, events_response: EventsResponse) -> BytesIO:
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
            c.drawString(100, y_position, f"Link: {event.link if event.link else 'N/A'}")
            y_position -= 20

            c.setFillColor(colors.black) 

            c.setStrokeColor(colors.gold)
            c.setLineWidth(1)
            c.line(100, y_position, width - 100, y_position)
            y_position -= 20 

        c.save()

        output_buffer.seek(0)
        return output_buffer


"""
The main issue was that the assistant was struggling to make subsequent search queries, as in targeting the search bar and clearing the previous search query. Prompting it to always open a new tab doesn't seem to work either.
The current solution was a implementation of a custom tool which will handle all searches that the assistant wants to do, by using the browser protocol with playwright.
    - Pros: Implemented as a Tool so Claude can deem when it is a appropriate time to use it, reliable and consistent, can be used for any search query; this is much faster
    - Cons: Assistant won't be able to interact with the search results, as the browser closes immediately after it's loaded. The only way Claude even gets the information is by the screenshot I append to the response.
        - not the worst thing as we don't want the asssitant to do a deep dive into the search results, just need to get the information from the search results. It seems to be working well now though.

Another solution for this is to run the sampling loop 3 times. One to find the city. Then give it the city to search 2? more times in seperate loops. This way search bar isn't an issue and it can interact with the search results.
    - Pros: This is probably as comprehensive as it gets, as the assistant will be able to interact with the search results, and can be used for any search query.
    - Cons: The assistant will take longer to complete the task, as it will have to run the sampling loop 3 times, but it is asynchronous; Will have to deal with dedeuplication of events;
            and an issue is that since deliveries in mutlithreaded, we might go above the scrapybara instance limit by doing this.
"""