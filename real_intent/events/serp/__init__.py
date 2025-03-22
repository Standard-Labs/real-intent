"""Implementation of event generation using olostep's serp api."""

import json
import requests
import datetime as dt
import time
from typing import List, Dict
import tldextract

from anthropic import Anthropic, APIStatusError

from real_intent.events.base import BaseEventsGenerator
from real_intent.internal_logging import log
from real_intent.events.models import Event, EventsResponse, OrganicLink
from real_intent.events.utils import extract_json_only, extract_json_array, retry_generation    
from real_intent.events.errors import NoValidJSONError, NoEventsFoundError, NoLinksFoundError, BatchNotCompleteError


class SerpEventsGenerator(BaseEventsGenerator):
    """Implementation of event generation using serp through olostep API"""

    def __init__(
        self, 
        serp_key: str,
        anthropic_key: str,
        start_date: dt.datetime | None = None,
        end_date: dt.datetime | None = None,
        geo_key: str | None = None,
    ):
        """
        Initialize the EventsGenerator.

        Args:
            serp_key: API key for olostep serp API,
            anthropic_key: API key for anthropic API
            start_date: Optional start date for event search, defaults to today
            end_date: Optional end date for event search, defaults to 14 days from start
            geo_key: Optional API key for geolocation service (e.g., zipcode lookup)

        """
        if not isinstance(serp_key, str) or not serp_key:
            raise ValueError("serp API key must be a truthy string.")

        if not isinstance(anthropic_key, str) or not anthropic_key:
            raise ValueError("anthropic API key must be a truthy string.")
        
        self.serp_key = serp_key
        self.geo_key = geo_key

        self.anthropic_client = Anthropic(api_key=anthropic_key)

        # Set dates with defaults if not provided
        start = start_date or dt.datetime.now()
        end = end_date or (start + dt.timedelta(days=14))
        
        # Validate inputs are datetime objects
        if not isinstance(start, dt.datetime) or not isinstance(end, dt.datetime):
            raise ValueError("Invalid start or end date inputs.")
        
        # Convert to formatted strings for internal use
        self.start_date = start.strftime("%B %d, %Y")
        self.end_date = end.strftime("%B %d, %Y")


    def get_city_state(self, zip_code: str) -> str | None:
        """
        Get the city and state for a given zip code.

        Args:
            zip_code (str): The zip code to look up.

        Returns:
            str | None: A string containing city and/or state and/or county information,
            or None if lookup fails.
        """
        try:
            if not self.geo_key:
                return None

            endpoint = f"https://api.api-ninjas.com/v1/zipcode?zip={zip_code}"
            headers = {
                "X-Api-Key": self.geo_key, 
            }
            response = requests.get(endpoint, headers=headers)
            response.raise_for_status()

            data = response.json()

            if not data or not isinstance(data, list) or len(data) == 0:
                return None

            data = data[0] # get the first result
            
            city_state = ""

            if not data:
                return None
            if data.get("city", None):
                city_state += f"{data.get('city')}, "
            if data.get("state", None):
                city_state += f"{data.get('state')}, "
            if data.get("county", None):
                city_state += f"{data.get('county')}"

            log("trace", f"City/State for zip code {zip_code}: {city_state}")
            return city_state
        except Exception as e:
            log("warn", f"Error getting city/state for zip code {zip_code}: {e}")
            return None


    def _request(self, endpoint: str, method: str = "GET", payload: dict = None):
        """Make a request to the specified endpoint for olostep api with the given method and payload."""
        try:
            log("debug", f"Making {method} request to {endpoint} with payload: {payload}")

            headers = {
                "Authorization": f"Bearer {self.serp_key}",
                "Content-Type": "application/json"
            }
            if method == "GET":
                response = requests.get(f"https://api.olostep.com/v1{endpoint}", headers=headers)
            else:
                response = requests.post(f"https://api.olostep.com/v1{endpoint}", json=payload, headers=headers)
            
            response.raise_for_status()

            log("debug", f"Response status for {method} request to {endpoint}: {response.status_code}")
            
            return response.json()
        except requests.exceptions.RequestException as e:
            log("error", f"Request error for {method} request to {endpoint}: {e}")
            raise


    def extract_links(self, query: str, n_links: int = 5) -> List[OrganicLink]:
        """Extract organic links from Google search results for the given query."""

        payload = {
            "formats": ["parser_extract"],
            "parser_extract": {
                "parser_id": "@olostep/google-search"
            },
            "screen_size": "desktop",
            "url_to_scrape": f"https://www.google.com/search?q={query}&gl=us&hl=en",
            "wait_before_scraping": 0
        }

        serp_response = self._request("/scrapes", method="POST", payload=payload)
        
        try:
            parsed_json_content = serp_response['result']['json_content']
            
            if isinstance(parsed_json_content, str):
                parsed_json_content = json.loads(parsed_json_content)
            else:
                log("warn", "Parsed json_content response is not a string, attempting to validate as dict.")
                
            organic_links = [
                OrganicLink(**item) for item in parsed_json_content.get('organic', [])
            ]

            filtered_domains = {"facebook", "wikipedia"}
            
            filtered_links = []
            
            for link in organic_links:
                if link.link:
                    domain = tldextract.extract(link.link).domain
                    if domain not in filtered_domains:
                        filtered_links.append(link)
                        filtered_domains.add(domain)

            log("trace", f" All Filtered Links Extracted: {filtered_links}")

            if not filtered_links:
                raise NoLinksFoundError(query)

            return filtered_links[:n_links]  # Limit to a maximum of n_links

        except KeyError as e:
            log("error", f"Key error extracting links: {str(e)}")
            raise
        except json.JSONDecodeError as e:
            log("error", f"JSON decode error extracting links: {str(e)}")
            raise


    def start_batch(self, organic_links: List[OrganicLink]) -> Dict[str, str]:
        """
            start batch processing for given organic links and return
            a mapping of custom_id to retrieve_id.
        """

        payload = {
            "items": [],
            "country": "US",
            "formats": ["parser_extract"],
            "parser_extract": {
                "parser_id": "@olostep/google-search"
            }
        }

        # form payload for batch request, mapping each organic link to a custom_id denoted by its index
        for i, link in enumerate(organic_links):
            if link.link:
                payload["items"].append({
                    "custom_id": str(i),
                    "url": link.link
                })
                
        serp_response = self._request("/batches", "POST", payload)

        batch_id = serp_response.get("id", None)
        if not batch_id:
            raise Exception("No valid batch ID found in the response.")

        log("debug", f"Started Batch ID: {batch_id}")

        self.poll_batch_status(batch_id)

        serp_response = self._request(f"/batches/{batch_id}/items", "GET")
        
        try:
            id_mapping = {item['custom_id']: item['retrieve_id'] for item in serp_response['items']}
        
        except KeyError as e: 
            log("error", f"Key error mapping retrieve_ids: {str(e)}")
            raise
        
        if not id_mapping:
            raise Exception("Could not form valid id_mapping.")
        
        log("debug", f"ID Mapping: {id_mapping}")
        return id_mapping


    def get_events(self, organic_links: List[OrganicLink], id_mapping: Dict[str, str], zip_code: str, city_state: str | None = None) -> str | None:

        def _get_content(retrieve_id: str) -> Dict[str, str]:
            """get the content for a given link position and retrieve id"""

            serp_response = self._request(f"/retrieve?retrieve_id={retrieve_id}&formats=markdown", "GET")

            markdown_content = serp_response.get("markdown_content", None)
            if not markdown_content:
                raise Exception(f"No markdown_content for retrieve_id: {retrieve_id}")
                                    
            return markdown_content
            
        prompt = (
            f"""You are an expert in aggregating community events, specializing in identifying relevant activities for zipcode {zip_code} {city_state if city_state else ""} between {self.start_date} and {self.end_date}.

            **Objective:**  
            Extract event details (title, date, description, link) from the provided messages, focusing on engaging events such as networking meetups, educational opportunities, car shows, outdoor festivals, art exhibitions, and family-friendly activities.

            **Instructions:**  
            - Analyze ALL the provided messages for event information (links, titles, and descriptions) within zipcode {zip_code} {city_state if city_state else ""}.  
            - Validate each event to ensure:  
                - It is relevant to the community.  
                - It falls within the correct timeframe ({self.start_date} to {self.end_date}).  
                - It is located in the specified area {city_state if city_state else ""}.  
                - Events **are not guaranteed** to meet these criteria, so you must carefully validate them.  
                - If an event is slightly outside the specified zipcode but remains **highly relevant to the community** (e.g., within the same county or a neighboring zipcode), you may include it **only as a last resort** and must be able to justify its inclusion.  
                - The date attribute represents the date or date range of the event in ISO 8601 format (YYYY-MM-DD). Make sure to follow this format when providing the date.

            **Important Notes:**
            - If you cannot find the specific link for an event, use the original link of the source of that content provided in the messages to reference the event. Only do this if you cannot find the specific link in the content.
            - Try to include events from a variety of the sources if possible, but above all prioritize the most relevant and engaging events for the community.
            
            **Exclusions:**  
            Do **not** include:  
                - Religious events.  
                - Dating-focused events.  
                - Events inappropriate for families.  
                - Events outside the specified location or timeframe.  

            **Output Format:**  
            - Return a **JSON list** of up to **5 most relevant** events, ranked by confidence.  
            - If fewer than 5 events meet the criteria, return only the valid ones.  
            - Ensure **no duplicate events** are included.  
            - If no suitable events are found, return an **empty JSON list**.  

            **Schema:**  
                Each event should be structured as a JSON object following this schema: {json.dumps(Event.model_json_schema())}  
            """
        )

        messages = [
            {"role": "assistant", "content": prompt}
        ]

        for i, link in enumerate(organic_links):
            retrieve_id = id_mapping.get(str(i))
            if retrieve_id:
                content = _get_content(retrieve_id)
                if content:
                    data = {
                        "title": link.title,
                        "link": link.link,
                        "content": content
                    }
                    messages.append({
                        "role": "user",
                        "content": json.dumps(data)  
                    })
        
        log("trace", "Sending messages to Anthropic for processing.")
        
        message = self.anthropic_client.messages.create(
            model="claude-3-7-sonnet-20250219",
            messages=messages,
            temperature=1,
            max_tokens=4000,
            thinking={
                "type": "enabled",
                "budget_tokens": 2000            
            },
        )

        log("debug", f"Anthropic response with thinking: {message}")

        content = message.content  
        if content:
            for block in content:
                if block.type == "text":
                    event_text = block.text
                    log("trace", f"Anthropic response: {event_text}")
                    return event_text
            log("error", "No text block found in Anthropic response.")
            raise Exception("No text block found in Anthropic response.")
        
        else:
            log("error", "No content returned from Anthropic.")
            raise Exception("No content returned from Anthropic.")
        

    def poll_batch_status(self, batch_id: str, max_retries: int = 5, initial_wait_time: int = 15) -> None: 
        """
        Polls the batch status until it is completed. Implemented with an initial wait time, 
        then poll every 10 seconds until the batch is completed or the maximum retries are reached.
        
        Mainly went with this approach due to the batch processing time taking around 15-30 seconds on average.

        Args:
            batch_id (str): The batch ID to check.
            max_retries (int): Maximum number of retries before raising an error.
            initial_wait_time (int): Initial wait time (in seconds) before polling again.

        Returns:
            None: Returns when batch is completed.

        Raises:
            BatchNotCompleteError: If the polling fails after the maximum retries.
        """
        wait_time = initial_wait_time
        retries = 0

        while retries < max_retries:
            try:
                # Poll the batch status
                status_response = self._request(f"/batches/{batch_id}", "GET")

                # Check if the batch status is completed
                if status_response.get("status") == "completed":
                    log("trace", f"Batch {batch_id} completed successfully.")
                    return
                
                log("debug", f"Batch {batch_id} status: {status_response.get('status')}. Retrying...")
            except Exception as e:
                log("error", f"Error while polling: {e}")

            retries += 1

            log("debug", f"Waiting for {wait_time} seconds before retrying...")
            time.sleep(wait_time)
            wait_time = 10 # poll every 10 seconds after the first attempt waits for initial_wait_time

        raise BatchNotCompleteError(batch_id)
   
   
    def summary_prompt(self, events: list[Event], zip_code: str, city_state: str | None = None) -> tuple[str, str]:
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
            Summarize the events happening in {zip_code} {city_state if city_state else ""} between {self.start_date} and {self.end_date} provided to you here.
            \n{events}\n
            Your summary should be informative and engaging, providing a brief overview of the events, the local community,
            and any other relevant details such as weather conditions. Provide a maximum of 5 sentences! Make sure to include the zipcode and the city/state in your summary.
            
            You must only include the key events and highlights from the list provided. Do not include any additional events.
            
            It should be structured in valid JSON format with one top level key called "summary" that contains a string
            summarizing the events and the local community during the specified period with a maximum of 5 sentences. 
            The summary should be a detailed paragraph that provides an overview of the expected weather conditions for the week, {self.start_date} to {self.end_date},
            and highlights the key events happening in {zip_code} {city_state if city_state else ""} from the list provided. Include any relevant insights about the local community, 
            such as cultural aspects, holiday-specific activities, or any notable attractions during this period.
            If there are any major holidays (e.g., Christmas, New Year's), mention how the local events and community activities reflect these.
        """

        return system, user


    def generate_summary(self, events: list[Event], zip_code: str, city_state: str | None = None) -> str:
        """Generate a summary of the events."""
        try:
            system, user = self.summary_prompt(events=events, zip_code=zip_code, city_state=city_state)        
            
            log("trace", "Generating summary with Anthropic.")
            
            messages = [
                {"role": "assistant", "content": system},
                {"role": "user", "content": user}
            ]
            
            message = self.anthropic_client.messages.create(
                model="claude-3-7-sonnet-20250219",
                messages=messages,
                temperature=1,
                max_tokens=1000,
            )

            content = message.content
            if content:
                for block in content:
                    if block.type == "text":
                        event_text = block.text
                        log("trace", f"Anthropic summary response: {event_text}")
                        return event_text
                log("error", "No text block found in Anthropic response.")
                raise Exception("No text block found in Anthropic response.")
            
            else:
                log("error", "No content returned from Anthropic.")
                raise Exception("No content returned from Anthropic.")
            
        except APIStatusError as e:
            log("error", f"APIStatusError generating summary with Anthropic: {e}", exc_info=e)
            raise
        except Exception as e:
            log("error", f"Error generating summary: {e}", exc_info=e)
            raise


    @retry_generation
    def _generate_events(self, zip_code: str) -> EventsResponse:
        """
        Internal method to process the event generation pipeline.
        
        Args:
            zip_code (str): The zip code to generate events for.
            
        Returns:
            EventsResponse: The generated events and summary.
            
        Raises:
            NoEventsFoundError: If no events could be found for the zip code.
            requests.exceptions.RequestException: If there is an issue with the API request.
            APIStatusError: If there is an issue with the Anthropic API.
            NoValidJSONError: If the response from the API is not valid JSON.
        """
        try:
            city_state = self.get_city_state(zip_code)

            links: List[OrganicLink] = self.extract_links(f"Events in {zip_code} {city_state if city_state else ''}")
       
            id_mappings = self.start_batch(links)
            response = self.get_events(links, id_mappings, zip_code, city_state)

            response = extract_json_array(response)
            events = [Event(title=event['title'], date=event['date'], description=event['description'], link=event['link']) for event in response]
            
            if not events:
                log("error", f"No events generated for {zip_code}.")
                raise NoEventsFoundError(f"No events found for {zip_code} between {self.start_date} and {self.end_date}.")
            
            log("debug", f"Generated {len(events)} for {zip_code} between {self.start_date} and {self.end_date}")

            summary = self.generate_summary(events, zip_code, city_state)
            summary_dict = extract_json_only(summary)
            
            log("debug", f"Events and summary generated successfully. Events: {events}, Summary: {summary_dict['summary']}")
            return EventsResponse(events=events, summary=summary_dict['summary'])
        
        except NoEventsFoundError:
            raise
        except requests.exceptions.RequestException as e:
            log("error", f"RequestException in _generate_events: {e}", exc_info=e)
            raise
        except APIStatusError as e:
            log("error", f"Anthropic APIStatusError in _generate_events: {e}", exc_info=e)
            raise
        except NoValidJSONError as e:
            log("error", f"NoValidJSONError in _generate_events: {e}", exc_info=e)
            raise
        except NoLinksFoundError as e:
            log("error", f"NoLinksFoundError in _generate_events: {e}", exc_info=e)
            raise
        except BatchNotCompleteError as e:
            log("error", f"BatchNotCompleteError in _generate_events: {e}", exc_info=e)
            raise
        except Exception as e:
            log("error", f"Error in _generate_events: {e}", exc_info=e)
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

