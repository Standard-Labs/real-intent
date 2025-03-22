"""Implementation of event generation using Scrapybara and Claude."""
import datetime as dt
import json

from anthropic import Anthropic, APIStatusError

from scrapybara import Scrapybara
from scrapybara.core.api_error import ApiError
from scrapybara.client import UbuntuInstance
from scrapybara.tools import ComputerTool
from scrapybara.types.act import ActResponse, Step, Model

from playwright.sync_api import sync_playwright, Error as PlaywrightError

from real_intent.events.scrapy_claude.claude_sync import SearchTool
from real_intent.events.models import Event, EventsResponse
from real_intent.events.base import BaseEventsGenerator
from real_intent.events.errors import NoEventsFoundError
from real_intent.events.utils import extract_json_only, retry_generation, ToolError, CLIResult, extract_json_array
from real_intent.internal_logging import log


# ---- Helpers ----

def log_step(step: Step) -> None:
    """Log the details of a step in the event generation process."""

    try:
        text: str = step.text
        tool_results = step.tool_results or []

        log("trace", f"Step Text: {text}")
        
        for tool_result in tool_results:

            result = tool_result.result
            
            if isinstance(result, CLIResult):
                if tool_result.is_error:
                    raise ToolError(f"Error for tool: {tool_result.tool_name} Got type CLIResult Error: {result.error}")
                else:
                    log("trace", f"Output for tool: {tool_result.tool_name}: {result.output}")

            elif isinstance(result, str):
                if tool_result.is_error:
                    raise ToolError(f"Error for tool: {tool_result.tool_name} Got type String result: {result}")
                else:
                    log("trace", f"Received Type String Output for tool: {tool_result.tool_name}: {result}")
                        
    except ToolError:
        raise

    except Exception as e:
        log("error", f"Error processing step: {e}", exc_info=e)


# ---- Implementation ----

class ScrapybaraEventsGenerator(BaseEventsGenerator):
    """Implementation of event generation using Scrapybara and Claude."""

    def __init__(
        self, 
        scrapybara_key: str, 
        anthropic_key: str, 
        start_date: dt.datetime | None = None,
        end_date: dt.datetime | None = None
    ):
        """
        Initialize the EventsGenerator.

        Args:
            scrapybara_key: API key for Scrapybara
            anthropic_key: API key for Anthropic
            instance_type: Type of Scrapybara instance to use
            start_date: Optional start date for event search, defaults to today
            end_date: Optional end date for event search, defaults to 14 days from start
        """
        if not isinstance(scrapybara_key, str) or not scrapybara_key:
            raise ValueError("Invalid Scrapybara API key. Please provide a valid API key.")
        
        if not isinstance(anthropic_key, str) or not anthropic_key:
            raise ValueError("Invalid Anthropic API key. Please provide a valid API key.")

        self.scrapybara_client = Scrapybara(api_key=scrapybara_key)
        self.anthropic_client = Anthropic(api_key=anthropic_key)
    
        self.instance = None

        # Set dates with defaults if not provided
        start = start_date or dt.datetime.now()
        end = end_date or (start + dt.timedelta(days=14))
        
        # Validate inputs are datetime objects
        if not isinstance(start, dt.datetime) or not isinstance(end, dt.datetime):
            raise ValueError("Invalid start or end date inputs.")
        
        # Convert to formatted strings for internal use
        self.start_date: str = start.strftime("%B %d, %Y")
        self.end_date: str = end.strftime("%B %d, %Y")

    def stop_instance(self) -> None:
        """ Stop the Scrapybara instance. """
        if self.instance:
            self.instance.stop()
            log("info", "Scrapybara instance stopped successfully.")
        else:
            log("info", "No Scrapybara instance to stop.")

    def initialize_instance(self) -> None:
        """ Intialize the Scrapybara instance and tools. """
        self.instance = self.scrapybara_client.start_ubuntu(timeout_hours=.06)

    def prompt(self, zip_code: str) -> tuple[str, str]:
        """Generate the prompts for event generation."""
        return f"""
            <SYSTEM_CAPABILITY>
            * You are utilising an Ubuntu virtual machine using linux architecture with internet access.
            * You can feel free to install Ubuntu applications with your bash tool. Use curl instead of wget.
            * Using bash tool you can start GUI applications, but you need to set export DISPLAY=:1 and use a subshell. For example "(DISPLAY=:1 xterm &)". GUI apps run with bash tool will appear within your desktop environment, but they may take some time to appear. Take a screenshot to confirm it did.
            * When using your bash tool with commands that are expected to output very large quantities of text, redirect into a tmp file and use str_replace_editor or `grep -n -B <lines before> -A <lines after> <query> <filename>` to confirm output.
            * When viewing a page it can be helpful to zoom out so that you can see everything on the page. Either that, or make sure you scroll down to see everything before deciding something isn't available.
            * When using your computer function calls, they take a while to run and send back to you. Where possible/feasible, try to chain multiple of these calls all into one function calls request.
            * The current date is {dt.datetime.today().strftime('%A, %B %-d, %Y')}.
            </SYSTEM_CAPABILITY>

            <YOUR_USECASE>
            User provides you not only with natural language prompt, but also an output schema of jsonschema format.
            This schema is derived from Pydantic model user has submitted to the system, and user intends to receive filled pydantic object.
            Your role is to respond when you are done EXCLUSIVELY with a JSON object which should fit the schema. Do not write usual response like in a chat.
            Essentially, you are a smart information retriever. After your JSON object answer is received, a Pydantic model will be instantiated based on it and returned to user.
            Never respond with common text. Always respond with a valid JSON object, according to user's instructions and schema.

            Note: The schema represents ONE object, you will provide a list of these objects, as in surround multiple objects with square brackets.
            </YOUR_USECASE>

            <JSON_SCHEMA>
            {json.dumps(Event.model_json_schema())}
            Note: The schema represents ONE object, you will provide a list of these objects.
            Note: The data attribute represents the date or date range of the event in ISO 8601 format (YYYY-MM-DD). Make sure to follow this format when providing the date.
            IMPORTANT: DO NOT ADD ANY ADDITIONAL TEXT IN YOUR FINAL MESSAGE TO USER, ONLY JSON OBJECTS THAT FIT THE SCHEMA PROVIDED.
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
            - All 'search' tool usage must include the city name at minimum, and the state and county name if found.
            
            <ATTENTION>
            IN YOUR LAST MESSAGE TO USER, FINAL RESPONSE, YOU MUST RESPOND EXCLUSIVELY WITH JSON SCHEMA WITHOUT SURROUNDING CONTENT OUTSIDE OF JSON SCHEMA, MANDATORY
            DO NOT INDENT RESPONSE STRING, no \n or whatever, just {{}} string.

            YOU MUST NEVER, EVER, EVER WRITE NATURAL RESPONSE TEXT IN YOUR FINAL MESSAGE TO USER (the one without subsequent tool calls) OUTSIDE OF JSON {{}} OBJECT, NOBODY READS STUFF OUTSIDE JSON OBJECT, OBEY THE SCHEMA NO MATTER WHAT!
            </ATTENTION>

        """, f""" 
            Task:
            1. Retrieve events happening in the city with ZIP code: {zip_code} from {self.start_date} to {self.end_date}. First, find the city, county, and state corresponding to ZIP code {zip_code} to ensure events are within the correct area. For every event validate the location to ensure it is in the correct city, county, and state.
            2. Focus on public events, community activities, festivals, and major holidays during this period (e.g., Christmas, New Year) if there are any. Ensure events are appropriate for families and the general public. Avoid political, religious, or controversial events.
            3. Include 3–5 unique events relevant to the specified ZIP code and timeframe. Include more if there are many events available that meet the criteria. 
            4. Exclude repeated or duplicate events.

            Requirements:
            - Perform TWO distinct searches:
            - First, search for events based on the city name derived from ZIP code {zip_code}. Include the city, county and state name in your query to ensure events are located in the correct area. The county and state names are there just to ensure you're searching for the correct events. Events must still be validated to ensure they're in the correct city!
              Find appropriate community events within the zip code area and timeframe, and if and only if this criteria is met, you will add that event to the list.
              Just because a event is shown in the search results does not mean it is in the correct area. You must validate the location of the event.
            - If the first search yields no results or not enough results, PERFORM a NEW SEARCH and refine your query and adjust search terms and perform a second search. Once again, only add events that meet the criteria.
            - If no results are found after two searches, stop searching and respond with an empty JSON list([]).
            - It is acceptable to return an empty list if there are no events matching the criteria. Avoid fabricated results or predictions of events. All your events must be real and verifiable.
            - Provide a JSON list of events matching the schema. You must include the link. If for some reason there is no link, set that attribute as null.
            - Ensure events are relevant to the area {zip_code} and date range {self.start_date} to {self.end_date}.

            Instructions:
            1. Start by finding the city, county and state name corresponding to the ZIP code {zip_code}.
            2. Perform the first search for public events, community activities, festivals, or major holidays in the city and timeframe.
            3. If the first search returns no results, refine or adjust the query and perform a second search.
            4. If the second search also yields no results, return an empty JSON list ([]).

            Final Output:
            - Submit a list of the JSON objects conforming to the provided schema. Do NOT provide any additional information or text outside of the JSON object.
            """

    def summary_prompt(self, events: list[Event], zip_code: str) -> tuple[str, str]:
        """
        Generate the prompt for summary generation.
        
        Args:
            events: List of events to summarize.
            zip_code: The zip code the events are for.
            
        Returns:
            A tuple of (system prompt, user prompt).
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
            Summarize the events happening in {zip_code} between {self.start_date} and {self.end_date} provided to you here.
            \n{events}\n
            Your summary should be informative and engaging, providing a brief overview of the events, the local community,
            and any other relevant details such as weather conditions. Provide a maximum of 5 sentences! 
            
            You must only include the key events and highlights from the list provided. Do not include any additional events.
            
            It should be structured in valid JSON format with one top level key called "summary" that contains a string
            summarizing the events and the local community during the specified period with a maximum of 5 sentences. 
            The summary should be a detailed paragraph that provides an overview of the expected weather conditions for the week, {self.start_date} to {self.end_date},
            and highlights the key events happening in {zip_code} from the list provided. Include any relevant insights about the local community, 
            such as cultural aspects, holiday-specific activities, or any notable attractions during this period.
            If there are any major holidays (e.g., Christmas, New Year's), mention how the local events and community activities reflect these.
        """

        return system, user

    def go_to_page(self, instance: UbuntuInstance, url: str) -> None:
        cdp_url = instance.browser.start().cdp_url
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(cdp_url)
            page = browser.new_page()
            page.goto(url)
            page.wait_for_load_state("load")

    def _run(self, zip_code: str) -> str:
        """Core implementation of the event generation loop, now abstracted through the act method."""
        self.initialize_instance()
        self.go_to_page(self.instance, "https://www.google.com")
        system, user = self.prompt(zip_code)

        output: ActResponse = self.scrapybara_client.act(
            tools=[
                ComputerTool(self.instance),
                SearchTool(self.instance)    
            ],
            model= Model(provider="anthropic", name="claude-3-5-sonnet-20241022", api_key=self.anthropic_client.api_key),
            system=system,
            prompt=user,
            on_step=lambda step: log_step(step)
        )

        return output.text

    def run(self, zip_code: str) -> str:
        """Run the event generation with error handling."""
        try:
            return self._run(zip_code)
        except KeyError as e:
            log("error", f"KeyError running Scrapybara event generation: {e}", exc_info=e)
            raise
        except ToolError as e:
            log("error", f"ToolError running Scrapybara event generation: {e}", exc_info=e)
            raise
        except ApiError as e:
            log("error", f"Scrapybara ApiError running Scrapybara event generation: {e}", exc_info=e)
            raise
        except APIStatusError as e:
            log("error", f"Anthropic APIStatusError running Scrapybara event generation: {e}", exc_info=e)
            raise
        except PlaywrightError as e:
            log("error", f"PlaywrightError running Scrapybara event generation: {e}", exc_info=e)
            raise
        except Exception as e:
            log("error", f"Error running Scrapybara event generation: {e}", exc_info=e)
            raise
        finally:
            self.stop_instance()

    @retry_generation
    def _generate_events(self, zip_code: str) -> EventsResponse:
        """
        Generate a list of events for the specified ZIP code and date range.
        """
        response = self.run(zip_code)
        response = extract_json_array(response)
        events = [Event(title=event['title'], date=event['date'], description=event['description'], link=event['link']) for event in response]
        log("info", f"Generated {len(events)} for {zip_code} between {self.start_date} and {self.end_date}")

        if not events:
            raise NoEventsFoundError(zip_code)
        
        summary = self.generate_summary(events, zip_code)
        summary_dict = extract_json_only(summary)

        log("debug", f"Events and summary generated successfully. Events: {events}, Summary: {summary_dict['summary']}")
        return EventsResponse(events=events, summary=summary_dict['summary'])

    def generate_summary(self, events: list[Event], zip_code: str) -> str:
        """Generate a summary of the events."""
        system, user = self.summary_prompt(events=events, zip_code=zip_code)        
        
        try:
            response = self.anthropic_client.completions.create(
            model="claude-2.1",  
            prompt=system + "\n\nHuman:" + user + "\n\nAssistant:", 
            max_tokens_to_sample=500,
            temperature=0.5,
        )

            
            return response.completion
        except APIStatusError as e:
            log("error", f"APIStatusError generating summary with Anthropic: {e}")
            raise

    def _generate(self, zip_code: str) -> EventsResponse:
        """
        Internal method to generate events for a given zip code.
        
        Args:
            zip_code: The zip code to generate events for.
            
        Returns:
            EventsResponse: The generated events and summary.
        """
        if not isinstance(zip_code, str) or not zip_code.isnumeric() or len(zip_code) != 5:
            raise ValueError("Invalid ZIP code. ZIP code must be a 5-digit numeric string.")

        return self._generate_events(zip_code)
