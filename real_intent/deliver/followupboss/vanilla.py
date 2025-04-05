"""Deliverer for FollowUpBoss CRM."""
import requests
import time

import random
import base64
from concurrent.futures import ThreadPoolExecutor

from real_intent.deliver.base import BaseOutputDeliverer
from real_intent.schemas import MD5WithPII
from real_intent.internal_logging import log
from real_intent.deliver.utils import rate_limited, EventType, InvalidCRMCredentialsError, CRMAccountInactiveError


class FollowUpBossDeliverer(BaseOutputDeliverer):
    """Delivers data to FollowUpBoss CRM."""

    def __init__(
            self, 
            api_key: str, 
            system: str, 
            system_key: str, 
            tags: list[str] | None = None,
            add_zip_tags: bool = True,
            base_url: str = "https://api.followupboss.com/v1",
            event_type: EventType = EventType.REGISTRATION,
            n_threads: int = 1,
            per_lead_insights: dict[str, str] | None = None
        ):
        """
        Initialize the FollowUpBossDeliverer.

        Args:
            api_key (str): The API key for FollowUpBoss.
            system (str): The system identifier.
            system_key (str): The system key.
            base_url (str, optional): The base URL for the FollowUpBoss API. Defaults to "https://api.followupboss.com/v1".
            event_type (EventType, optional): The event type for adding a lead. Defaults to EventType.REGISTRATION.
            n_threads (int, optional): The number of threads to use for delivering leads. Defaults to 1.
        """
        self.api_key: str = api_key
        self.base_url: str = base_url
        self.system: str = system
        self.tags: list[str] = tags or []
        self.add_zip_tags: bool = add_zip_tags
        self.system_key: str = system_key
        self.per_lead_insights: dict[str, str] = per_lead_insights or {}

        # Configuration stuff
        self.event_type: EventType = EventType(event_type)
        self.n_threads: int = n_threads

        # Make sure API credentials are valid
        if not self._verify_api_credentials():
            raise InvalidCRMCredentialsError("Invalid API credentials provided for FollowUpBoss.")

        # Make sure the account is active
        if not self._verify_account_active():
            raise CRMAccountInactiveError("FollowUpBoss account is inactive.")
        
    @property
    def api_headers(self) -> dict:
        """
        Generate the API headers for FollowUpBoss requests.

        Returns:
            dict: A dictionary containing the necessary headers for API requests.
        """
        return {
            "Authorization": f"Basic {base64.b64encode(f'{self.api_key}:'.encode()).decode()}",
            "Content-Type": "application/json",
            "X-System": self.system,
            "X-System-Key": self.system_key
        }
    
    @rate_limited(crm="FollowUpBoss")
    def _verify_api_credentials(self) -> bool:
        """
        Verify that the API credentials are valid.

        Returns:
            bool: True if the credentials are valid, False otherwise.
        """
        response = requests.get(
            f"{self.base_url}/identity",
            headers=self.api_headers
        )

        return response.ok

    @rate_limited(crm="FollowUpBoss")
    def _verify_account_active(self) -> bool:
        """
        Verify that the account is active.

        Returns:
            bool: True if the account is active, False otherwise.
        """
        response = requests.get(
            f"{self.base_url}/people",
            headers=self.api_headers
        )
        log("trace", f"Raw response: {response.text}, status_code: {response.status_code}")

        return response.ok  # 403 if inactive
    
    def _warn_dnc(self, pii_md5s: list[MD5WithPII]) -> None:
        """Log a warning if any of the leads are on the DNC list."""
        for md5_with_pii in pii_md5s:
            if any(phone.do_not_call for phone in md5_with_pii.pii.mobile_phones):
                log(
                    "warn",
                    (
                        f"At least 1 lead in the Follow Up Boss deliverer was on "
                        f"the DNC list. Please validate the lead before delivery."
                    )
                )
                break

    def _deliver(self, pii_md5s: list[MD5WithPII]) -> list[dict]:
        """
        Deliver the PII data to FollowUpBoss.

        Args:
            pii_md5s (list[MD5WithPII]): A list of MD5WithPII objects containing the PII data to be delivered.

        Returns:
            list[dict]: A list of response dictionaries from the FollowUpBoss API for each delivered event.
        """
        # Log if any of the leads are on the DNC list
        self._warn_dnc(pii_md5s)

        with ThreadPoolExecutor(max_workers=self.n_threads) as executor:
            return list(executor.map(self._deliver_single_lead, pii_md5s))

    def _deliver_single_lead(self, md5_with_pii: MD5WithPII) -> dict:
        """
        Deliver a single lead to FollowUpBoss.

        Args:
            md5_with_pii (MD5WithPII): The MD5WithPII object containing the PII data for a single lead.

        Returns:
            dict: A response dictionary from the FollowUpBoss API for the delivered event.
        """
        event_data = self._prepare_event_data(md5_with_pii)
        response = self._send_event(event_data)
        log(
            "trace", 
            (
                f"Delivered lead: {md5_with_pii.md5}, event_type: {self.event_type.value}, "
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
            dict: A dictionary containing the prepared event data for the FollowUpBoss API.
        """
        log("trace", f"Preparing event data for MD5: {md5_with_pii.md5}, first_name: {md5_with_pii.pii.first_name}, last_name: {md5_with_pii.pii.last_name}")
        person_data = {}
        if md5_with_pii.pii.first_name:
            person_data["firstName"] = md5_with_pii.pii.first_name
        if md5_with_pii.pii.last_name:
            person_data["lastName"] = md5_with_pii.pii.last_name
        if md5_with_pii.pii.emails:
            person_data["emails"] = [{"value": email} for email in md5_with_pii.pii.emails]
        if md5_with_pii.pii.mobile_phones:
            person_data["phones"] = [{"value": phone.phone} for phone in md5_with_pii.pii.mobile_phones]
        if md5_with_pii.pii.address and md5_with_pii.pii.city and md5_with_pii.pii.state and md5_with_pii.pii.zip_code:
            person_data["addresses"] = [{
                "type": "home",
                "street": md5_with_pii.pii.address,
                "city": md5_with_pii.pii.city,
                "state": md5_with_pii.pii.state,
                "code": md5_with_pii.pii.zip_code
            }]

        # Prepare sentences
        sentences: list[str] = []
        for sentence in md5_with_pii.sentences:
            if ">" in sentence:
                sentences.append(sentence.split(">")[-1])
                continue
            
            sentences.append(sentence)
        
        sentences_str = ", ".join(sentences)
        sentences_str = f"Intents: {sentences_str}."

        # Prepare tags: all tags + zip code if available and add_zip_tags is True
        tags_to_add: list[str] = [] + self.tags
        if md5_with_pii.pii.zip_code and self.add_zip_tags:
            tags_to_add.append(md5_with_pii.pii.zip_code)

        # Add tags to person data
        person_data["tags"] = tags_to_add

        return {
            "source": self.system,
            "system": self.system,
            "description": sentences_str,
            "type": self.event_type.value,
            "person": person_data
        }

    @rate_limited(crm="FollowUpBoss")
    def _send_event(self, event_data: dict) -> dict:
        """
        Send an event to the FollowUpBoss API.

        Args:
            event_data (dict): The prepared event data to be sent to the API.

        Returns:
            dict: The response from the FollowUpBoss API, either the JSON response or an ignored status message.

        Raises:
            requests.exceptions.HTTPError: If the API request fails.
        """
        log(
            "trace", 
            (
                f"Sending event to FollowUpBoss API, event_type: {event_data['type']}, "
                f"person: {event_data['person']}"
            )
        )

        response = requests.post(
            f"{self.base_url}/events", 
            json=event_data, 
            headers=self.api_headers
        )
        
        log("trace", f"Raw response: {response.text}, status_code: {response.status_code}")
        
        if response.status_code == 204:
            log("debug", "Lead flow associated with this source has been archived and ignored.")
            return {
                "status": "ignored", 
                "message": (
                    "Lead flow associated with this source has been "
                    "archived and ignored."
                )
            }
        
        response.raise_for_status()
        return response.json()

    @rate_limited(crm="FollowUpBoss")
    def _add_note(self, person_id: int, body: str, subject: str = "", retry: bool = True) -> bool:
        """
        Add a note to a person in Follow Up Boss.

        Args:
            person_id (str): The ID of the person to add the note to.
            body (str): The body of the note.
            subject (str, optional): The subject of the note. Defaults to "".
            retry (bool, optional): Whether to retry on failure. Defaults to True.

        Returns:
            bool: True if the note was added successfully, False otherwise.
        """
        note_data = {
            "personId": int(person_id),
            "body": body,
            "subject": subject
        }

        response = requests.post(
            f"{self.base_url}/notes",
            headers=self.api_headers,
            json=note_data
        )

        # If rate limited, raise the exception so the caller can handle it
        if response.status_code == 429:
            response.raise_for_status()

        if response.ok:
            log("trace", f"Successfully added note to person {person_id}")
            return True

        # Retry on contact not found error
        if retry and "contact not found" in response.text.lower():
            log("warn", f"Contact not found for person {person_id}. Retrying...")
            time.sleep(random.uniform(5, 7))
            return self._add_note(person_id, body, subject, retry=False)

        # Otherwise log the error and proceed
        log("error", f"Failed to add note to person {person_id}: {response.text}")
        return False
