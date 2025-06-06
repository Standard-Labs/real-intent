"""Deliverer for CINC CRM."""
import requests
import datetime

from concurrent.futures import ThreadPoolExecutor

from typing import Any

from real_intent.deliver.base import BaseOutputDeliverer
from real_intent.schemas import MD5WithPII
from real_intent.internal_logging import log
from real_intent.deliver.utils import rate_limited, InvalidCRMCredentialsError


class CINCDeliverer(BaseOutputDeliverer):
    """Delivers data to CINC CRM."""

    def __init__(
            self, 
            api_key: str, 
            system: str,
            tags: list[str] | None = None,
            add_zip_tags: bool = True,
            base_url: str = "https://public.cincapi.com/v2/site",
            n_threads: int = 1,
            per_lead_insights: dict[str, str] | None = None
        ):
        """
        Initialize the CINCDeliverer.

        Args:
            api_key (str): The API key for CINC.
            system (str): The system name for source (Real Intent or Webhawk).
            tags (list[str], optional): A list of tags to be added to the lead. Defaults to None.
            add_zip_tags (bool, optional): Whether to add zip code tags. Defaults to True.
            base_url (str, optional): The base URL for the CINC API. Defaults to "https://public.cincapi.com/v2/site".
            n_threads (int, optional): The number of threads to use for delivering leads. Defaults to 1.
            per_lead_insights (dict[str, str], optional): A dictionary of insights to be added to the lead. Defaults to None.            
        """
        
        self.api_key: str = api_key
        self.system: str = system
        self.base_url: str = base_url
        self.tags: list[str] = tags or []
        self.add_zip_tags: bool = add_zip_tags
        self.per_lead_insights: dict[str, str] = per_lead_insights or {}

        # Configuration stuff
        self.n_threads: int = n_threads

        # Make sure API credentials are valid
        if not self._verify_api_credentials():
            raise InvalidCRMCredentialsError("Invalid API credentials provided for CINC.")
        
    @property
    def api_headers(self) -> dict:
        """
        Generate the API headers for requests.

        Returns:
            dict: A dictionary containing the necessary headers for API requests.
        """
        return {
            "Authorization": f"{self.api_key}",
            "Content-Type": "application/json",
        }
    
    @rate_limited(crm="CINC")
    def _verify_api_credentials(self) -> bool:
        """
        Verify that the API credentials are valid.

        Returns:
            bool: True if the credentials are valid, False otherwise.
        """
        
        response = requests.get(
            f"{self.base_url}/me",
            headers=self.api_headers
        )

        return response.ok
    
    def _warn_dnc(self, pii_md5s: list[MD5WithPII]) -> None:
        """Log a warning if any of the leads are on the DNC list."""
        for md5_with_pii in pii_md5s:
            if any(phone.do_not_call for phone in md5_with_pii.pii.mobile_phones):
                log(
                    "warn",
                    (
                        f"At least 1 lead in the CINC deliverer was on "
                        f"the DNC list. Please validate the lead before delivery."
                    )
                )
                break

    def _deliver(self, pii_md5s: list[MD5WithPII]) -> list[dict]:
        """
        Deliver the PII data to CINC.

        Args:
            pii_md5s (list[MD5WithPII]): A list of MD5WithPII objects containing the PII data to be delivered.

        Returns:
            list[dict]: A list of response dictionaries from the CINC API for each delivered event.
        """
        # Log if any of the leads are on the DNC list
        self._warn_dnc(pii_md5s)

        with ThreadPoolExecutor(max_workers=self.n_threads) as executor:
            return list(executor.map(self._deliver_single_lead, pii_md5s))

    def _deliver_single_lead(self, md5_with_pii: MD5WithPII) -> dict:
        """
        Deliver a single lead to CINC.

        Args:
            md5_with_pii (MD5WithPII): The MD5WithPII object containing the PII data for a single lead.

        Returns:
            dict: A response dictionary from the CINC API for the delivered event.
        """
        event_data = self._prepare_event_data(md5_with_pii)
        response = self._send_event(event_data)
        log(
            "trace", 
            (
                f"Delivered lead: {md5_with_pii.md5}"
                f"response_status: {response.get('status', 'unknown')}"
            )
        )
        return response

    def _prepare_event_data(self, md5_with_pii: MD5WithPII) -> dict:
        """
        Prepare the event data for a single MD5WithPII object.

        Args:
            md5_with_pii (MD5WithPII): The MD5WithPII object containing the PII data.

        Returns:
            dict: A dictionary containing the prepared event data for the CINC API.
        """
        log("trace", f"Preparing event data for MD5: {md5_with_pii.md5}, first_name: {md5_with_pii.pii.first_name}, last_name: {md5_with_pii.pii.last_name}")
        
        # Prepare contact info
        contact_info: dict[str, Any] = {}
        
        contact_info["first_name"] = md5_with_pii.pii.first_name or ""
        contact_info["last_name"] = md5_with_pii.pii.last_name or ""
        
        if md5_with_pii.pii.emails:
            contact_info["email"] = md5_with_pii.pii.emails[0]
        
        if md5_with_pii.pii.mobile_phones:
            phone_numbers: dict[str, str | None] = {"cell_phone": None, "home_phone": None, "work_phone": None, "office_phone": None}
        
            for i, key in enumerate(phone_numbers.keys()):
                if i < len(md5_with_pii.pii.mobile_phones):
                    phone_numbers[key] = md5_with_pii.pii.mobile_phones[i].phone
            contact_info["phone_numbers"] = phone_numbers
            
        if md5_with_pii.pii.address and md5_with_pii.pii.city and md5_with_pii.pii.state and md5_with_pii.pii.zip_code:
            contact_info["mailing_address"] = {
                "street": md5_with_pii.pii.address,
                "city": md5_with_pii.pii.city,
                "state": md5_with_pii.pii.state,
                "postal_or_zip": md5_with_pii.pii.zip_code
            }
        
        # Add Notes (Intent Sentences and Insight)
        notes: list[dict[str, str]] = []

        sentences: list[str] = []
        for sentence in md5_with_pii.sentences:
            if ">" in sentence:
                sentences.append(sentence.split(">")[-1])
                continue
            sentences.append(sentence)
        sentences_str = ", ".join(sentences)

        if sentences:
            notes.append({
                "content": sentences_str,
                "category": "info",
                "created_by": self.system,
                "created_date": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
            
        if (insight := self.per_lead_insights.get(md5_with_pii.md5)):
            notes.append({
                "content": insight,
                "category": "info",
                "created_by": self.system,
                "created_date": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "is_pinned": True,
            })  
            
        # Add tags as labels
        if self.tags:
            pass
        if self.add_zip_tags and md5_with_pii.pii.zip_code:
            pass        
            
        # Prepare event data according to CINC API schema
        event_data: dict[str, Any] = {
            "registered_date": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),            
            "info":{
                "status": "unworked",
                "source": self.system,
                "contact": contact_info,
            },
            "notes": notes,
        }
                        
        return event_data

    @rate_limited(crm="CINC")
    def _send_event(self, event_data: dict) -> dict:
        """
        Send an event to the CINC API.

        Args:
            event_data (dict): The prepared event data to be sent to the API.

        Returns:
            dict: The response from the CINC API, either the JSON response or an ignored status message.

        Raises:
            requests.exceptions.HTTPError: If the API request fails.
        """
        log(
            "trace", 
            (
                f"Sending event to the CINC API"
                f"person: {event_data}"
            )
        )

        response = requests.post(
            f"{self.base_url}/leads", 
            json=event_data, 
            headers=self.api_headers
        )
        
        log("trace", f"Raw response: {response.text}, status_code: {response.status_code}")
                
        response.raise_for_status()
        return response.json()
