"""Follow Up Boss delivery with AI field mapping. Requires OpenAI."""
import requests
from pydantic import BaseModel, Field

import json
from typing import Literal, Any
import time

from real_intent.schemas import MD5WithPII
from real_intent.deliver.followupboss.vanilla import FollowUpBossDeliverer, EventType, rate_limited
from real_intent.deliver.followupboss.ai_prompt import SYSTEM_PROMPT
from real_intent.internal_logging import log, log_span


# ---- Models ----

class CustomField(BaseModel):
    """Custom field in Follow Up Boss."""
    id: int
    name: str
    label: str
    type: str
    choices: list[str] = Field(default_factory=list)
    orderWeight: int
    hideIfEmpty: bool
    readOnly: bool
    isRecurring: bool = False


class CustomFieldCreation(BaseModel):
    """Job to create a custom field in Follow Up Boss."""
    label: str = Field(
        ..., 
        description="The user-friendly name of the custom field (e.g. 'Anniversary')."
    )
    type: Literal["text", "date", "number", "dropdown"] = Field(
        ...,
        description="The type of the custom field. Can be 'text', 'date', 'number', or 'dropdown'."
    )
    choices: list[str] = Field(
        default_factory=list,
        description="List of choices for the custom field. Only if type is 'dropdown'."
    )
    isRecurring: bool = Field(
        False,
        description=(
            "Whether the custom field is recurring (e.g. 'Birthday'). "
            "Only set and returned for date fields."
        )
    )


# ---- Errors ----

class InvalidOpenAICredentialsError(Exception):
    """Raised when invalid OpenAI API credentials are provided."""


# ---- Deliverer ----

class AIFollowUpBossDeliverer(FollowUpBossDeliverer):
    """
    Delivers data to FollowUpBoss CRM and uses AI to match fields with the user's
    custom fields. Reads the user's custom fields and matches them with fields in PII data.

    (Eventually will optionally create new custom fields for the user's FUB account 
    if they don't exist, and then maps the fields in the PII data to the custom fields.)
    """

    def __init__(
        self,
        api_key: str,
        system: str,
        system_key: str,
        openai_api_key: str,
        tags: list[str] | None = None,
        add_zip_tags: bool = True,
        base_url: str = "https://api.followupboss.com/v1",
        event_type: EventType = EventType.REGISTRATION,
        n_threads: int = 1,
        per_lead_insights: dict[str, str] | None = None,
        **kwargs
    ):
        """
        Initialize the AIFollowUpBossDeliverer.

        Args:
            api_key (str): The API key for FollowUpBoss.
            system (str): The system identifier.
            system_key (str): The system key.
            openai_api_key (str): The API key for OpenAI.
            base_url (str, optional): The base URL for the FollowUpBoss API. Defaults to "https://api.followupboss.com/v1".
            event_type (EventType, optional): The event type for adding a lead. Defaults to Registration.
            n_threads (int, optional): The number of threads to use for delivering leads. Defaults to 1.
            per_lead_insights (dict[str, str], optional): Per-lead insights to be added as notes. Defaults to {}.
            **kwargs: Additional keyword arguments to be passed to the parent class.
        """
        super().__init__(
            api_key=api_key,
            system=system,
            system_key=system_key,
            tags=tags,
            add_zip_tags=add_zip_tags,
            base_url=base_url,
            event_type=event_type,
            n_threads=n_threads,
            per_lead_insights=per_lead_insights,
            **kwargs
        )

        try:
            import openai
        except ImportError:
            log("error", "OpenAI is required for AI FollowUpBoss deliverer. pip install real-intent[ai].")
            raise ImportError(
                "OpenAI is required for AI FollowUpBoss deliverer. pip install real-intent[ai]."
            )

        # Set the OpenAI client and verify the credentials
        self.openai_client = openai.OpenAI(api_key=openai_api_key)

        if not self._verify_openai_credentials():
            raise InvalidOpenAICredentialsError("Invalid API credentials provided for OpenAI.")

        # Cache the custom fields
        self.custom_fields: list[CustomField] = []

    def _verify_openai_credentials(self) -> bool:
        """Make sure the OpenAI API key is valid."""
        response = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {self.openai_client.api_key}"}
        )

        if not response.ok:
            time.sleep(2)
            return requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {self.openai_client.api_key}"}
            ).ok

        return True

    def _deliver_single_lead(self, md5_with_pii: MD5WithPII) -> dict:
        """
        Deliver a single lead to FollowUpBoss, attempting AI-based delivery first and falling back to standard delivery if needed.

        Args:
            md5_with_pii (MD5WithPII): The MD5WithPII object containing the PII data for a single lead.

        Returns:
            dict: A response dictionary from the FollowUpBoss API for the delivered event.
        """
        with log_span(f"Delivering lead with AI field mapping: {md5_with_pii}", _level="trace"):
            try:
                event_data = self._prepare_event_data(md5_with_pii)
                response = self._send_event(event_data)

                # Per-lead insight
                person_id: int = int(response["id"])
                if (insight := self.per_lead_insights.get(md5_with_pii.md5)):
                    self._add_note(person_id=person_id, body=insight, subject="Real Intent Insight")

                log(
                    "trace", 
                    (
                        f"Delivered lead with AI mapping: {md5_with_pii.md5}, "
                        f"event_type: {self.event_type.value}, "
                        f"response_status: {response.get('status', 'unknown')}"
                    )
                )
                return response
            except Exception as e:
                log("error", f"Error in AI field mapping delivery for lead {md5_with_pii.md5}: {str(e)}. Falling back to standard delivery.")
                return super()._deliver_single_lead(md5_with_pii)

    @rate_limited(crm="AI FollowUpBoss")
    def _get_custom_fields(self) -> list[CustomField]:
        """
        Get the custom fields from the user's Follow Up Boss account.

        Returns:
            list[CustomField]: A list of CustomField objects representing the custom fields in the user's account.

        Raises:
            requests.RequestException: If there's an error in the API request.
        """
        if self.custom_fields:
            log("trace", f"Using cached custom fields: {self.custom_fields}")
            return self.custom_fields

        with log_span("Fetching custom fields from Follow Up Boss", _level="trace"):
            response = requests.get(f"{self.base_url}/customFields", headers=self.api_headers)
            response.raise_for_status()
            raw_res = response.json()["customfields"]
            custom_fields = [CustomField(**field) for field in raw_res]
            log("debug", f"Fetched {len(custom_fields)} custom fields")
            
            # Trace logging for custom fields
            for field in custom_fields:
                log("trace", f"Custom field: id={field.id}, name='{field.name}', label='{field.label}', type='{field.type}'")

            self.custom_fields = custom_fields
            return self.custom_fields

    @rate_limited(crm="AI FollowUpBoss")
    def _create_custom_field(self, custom_field: CustomFieldCreation) -> CustomField:
        """
        Create a custom field in the user's Follow Up Boss account.

        Args:
            custom_field (CustomFieldCreation): The custom field to be created.

        Returns:
            CustomField: The created custom field.

        Raises:
            requests.RequestException: If there's an error in the API request.
        """
        log("debug", f"Creating custom field: {custom_field.label}")

        # Create the custom field
        response = requests.post(
            f"{self.base_url}/customFields",
            headers=self.api_headers,
            json=custom_field.model_dump()
        )
        response.raise_for_status()
        field_id = response.json()["id"]
        
        # Get the custom field
        response = requests.get(
            f"{self.base_url}/customFields/{field_id}",
            headers=self.api_headers
        )
        response.raise_for_status()

        created_field = CustomField(**response.json())
        log("debug", f"Created custom field: {created_field.label} with ID: {created_field.id}")
        return created_field
    
    def _prepare_event_data(self, md5_with_pii: MD5WithPII) -> dict:
        """
        Prepare the event data for a single MD5WithPII object using AI field mapping.

        This method extends the parent class's _prepare_event_data method by adding AI-suggested
        custom field mappings to the event data.

        Args:
            md5_with_pii (MD5WithPII): The MD5WithPII object containing the PII data.

        Returns:
            dict: A dictionary containing the prepared event data for the FollowUpBoss API,
                  including AI-suggested custom field mappings.
        """
        log("debug", f"Preparing event data with AI mapping for MD5: {md5_with_pii.md5}")
        raw_event_data: dict = super()._prepare_event_data(md5_with_pii)

        # Get all the custom fields
        custom_fields: list[CustomField] = self._get_custom_fields()
        custom_fields_str: str = json.dumps(
            [field.model_dump() for field in custom_fields],
            indent=4
        )

        # Prepare the PII data
        filtered_pii_data: dict[str, Any] = {
            key: val for key, val in md5_with_pii.pii.model_dump().items() 
            if key not in {"first_name", "last_name", "emails", "mobile_phones", "addresses"}
        }
        filtered_pii_data_str: str = json.dumps(filtered_pii_data, indent=4)

        # Match the custom fields with the PII data
        log("debug", "Sending request to OpenAI for field mapping")
        response = self.openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": (
                        f"PII data:\n{filtered_pii_data_str}\n\n"
                        f"Custom fields:\n{custom_fields_str}"
                    )
                }
            ],
            max_tokens=4095,
            temperature=0.7,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0,
            response_format={"type": "json_object"}
        )

        # Try to parse
        try:
            ai_suggestions: dict[str, str | int | bool] = json.loads(
                response.choices[0].message.content
            )
            log("debug", f"Received {len(ai_suggestions)} AI suggestions for field mapping")
            
            # Trace logging for AI suggestions
            for key, value in ai_suggestions.items():
                log("trace", f"AI suggestion: {key} -> {value}")
        except json.JSONDecodeError:
            log("error", "Failed to parse OpenAI response for field mapping")
            ai_suggestions: dict[str, str | int | bool] = {}
        
        # Merge the AI suggestions with the protected person data
        custom_field_names: list[str] = [field.name for field in custom_fields]
        for key, val in ai_suggestions.items():
            if key in custom_field_names:
                raw_event_data["person"][key] = val
                log("trace", f"Mapped field: {key} -> {val}")
            else:
                log("warn", f"Unmapped field: {key} -> {val}")

        log("debug", f"Prepared event data with {len(raw_event_data['person'])} fields")
        return raw_event_data
