"""Use an LLM to generate insights from PII data."""
from pydantic import BaseModel, Field, ValidationError

from real_intent.analyze.base import BaseAnalyzer
from real_intent.schemas import MD5WithPII

from real_intent.analyze.insights.prompt import SYSTEM_PROMPT
from real_intent.analyze.insights.validator_prompt import SYSTEM_PROMPT as VALIDATOR_PROMPT

from real_intent.deliver.csv import CSVStringFormatter
from real_intent.validate.base import BaseValidator
from real_intent.process.base import BaseProcessor, ProcessValidator
from real_intent.internal_logging import log
from real_intent.utils import retry_with_backoff

from real_intent.deliver.csv_redacted import CSVStringFormatterRedacted

class LeadInsights(BaseModel):
    """Insights generated from lead data."""
    thoughts: str = Field(
        ...,
        description=(
            "String of any thinking that'll help you work through the leads, any "
            "patterns, and arrive at your insights. Think of this as a scratchpad you "
            "can use to note down things you notice to be thorough and refined in your "
            "final insights, and to calculate real numbers (percentages etc.)."
        )
    )
    insights: list[str] = Field(
        ...,
        description=(
            "List of strings where each string is a detailed insight derived from "
            "the lead data. These insights focus on IAB intent categories and personal "
            "information of each lead. They provide actionable information to help "
            "understand how to sell to these leads effectively. Insights combine "
            "multiple attributes (e.g., marital status, net worth, and intent "
            "categories) to make informed assumptions about what the leads would want. "
            "The language used is tailored for the person who will be using these "
            "leads, providing critical and analytical observations that can guide "
            "marketing strategies and personalized outreach efforts. Each insight "
            "should be a complete, self-contained statement without any leading "
            "numbers or bullet points."
        )
    )


class OpenAIInsightsGenerator(BaseAnalyzer):
    """Generates insights from PII data using OpenAI."""

    def __init__(self, openai_api_key: str):
        """
        Initialize the OpenAIInsightsGenerator.

        Args:
            openai_api_key: The API key for OpenAI.

        Raises:
            ImportError: If the OpenAI package is not installed.
        """
        try:
            from openai import OpenAI, OpenAIError
        except ImportError:
            log("error", "Failed to import OpenAI. Make sure to install the package with the 'ai' extra.")
            raise ImportError("Please install this package with the 'ai' extra.")
        
        self.openai_client: OpenAI = OpenAI(api_key=openai_api_key)
        self._OpenAI_Error = OpenAIError

    def _analyze(self, pii_md5s: list[MD5WithPII]) -> str:
        """
        Internal method to analyze the list of MD5s with PII and generate insights using an LLM.

        Args:
            pii_md5s: List of MD5 hashes with associated PII data.

        Returns:
            Generated insights as a string.
        """
        log("debug", f"Starting analysis for {len(pii_md5s)} MD5s")
        csv_data = CSVStringFormatter().deliver(pii_md5s)
        log("trace", f"CSV data prepared, length: {len(csv_data)}")
        
        @retry_with_backoff()
        def generate_insights():
            return self.openai_client.beta.chat.completions.parse(
                model="gpt-4o-2024-08-06",
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": csv_data
                    }
                ],
                max_tokens=4095,
                temperature=1,
                top_p=1,
                frequency_penalty=0,
                presence_penalty=0,
                response_format=LeadInsights
            )

        try:
            result = generate_insights()
            lead_insights: LeadInsights | None = result.choices[0].message.parsed
        except (self._OpenAI_Error, ValidationError) as e:
            log("error", f"Failed to generate insights after retries. Error: {e}")
            return "Failed to generate insights. Please try again later."

        if not lead_insights:
            log("error", "OpenAI response did not contain valid insights")
            return "No insights on these leads at the moment."

        log("info", f"Generated {len(lead_insights.insights)} insights")
        log("trace", f"Thoughts from OpenAI: {lead_insights.thoughts}")

        for i, insight in enumerate(lead_insights.insights, start=1):
            log("trace", f"Insight {i}: {insight}")

        processed_insights: list[str] = [
            f"{i+1}. {insight}" for i, insight in enumerate(lead_insights.insights)
        ]

        final_insights = "\n".join(processed_insights)
        log("debug", f"Final insights:\n{final_insights}")
        return final_insights


class ValidatedLeadInsights(BaseModel):
    """Insights generated from lead data."""
    thoughts: str = Field(
        ...,
        description=(
            "String of any thinking that'll help you work through the leads, any "
            "patterns, and arrive at your insights. Think of this as a scratchpad you "
            "can use to note down things you notice to be thorough and refined in your "
            "final insights, and to calculate real numbers (percentages etc.)."
        )
    )
    validation_insight: str = Field(
        ...,
        description=(
            "Intuitive, in-context insight on the validation process "
            "and its results. Avoid using the validator names themselves, instead "
            "use a high-level approach to describe what validations happened and why. "
            "That said, do be specific about the criteria and the results."
        )
    )
    insights: list[str] = Field(
        ...,
        description=(
            "List of strings where each string is a detailed insight derived from "
            "the lead data. These insights focus on IAB intent categories and personal "
            "information of each lead. They provide actionable information to help "
            "understand how to sell to these leads effectively. Insights combine "
            "multiple attributes (e.g., marital status, net worth, and intent "
            "categories) to make informed assumptions about what the leads would want. "
            "The language used is tailored for the person who will be using these "
            "leads, providing critical and analytical observations that can guide "
            "marketing strategies and personalized outreach efforts. Each insight "
            "should be a complete, self-contained statement without any leading "
            "numbers or bullet points."
        )
    )


class ValidatedInsightsGenerator(BaseAnalyzer):
    """Generates insights from PII data using OpenAI. Incorporates knowledge of validators."""

    def __init__(
            self, 
            openai_api_key: str, 
            processor: BaseProcessor,
        ):
        """
        Initialize the ValidatedInsightsGenerator.

        Args:
            openai_api_key: The API key for OpenAI.
            processor: The processor containing validators.

        Raises:
            ImportError: If the OpenAI package is not installed.
        """
        try:
            from openai import OpenAI
        except ImportError:
            log("error", "Failed to import OpenAI. Make sure to install the package with the 'ai' extra.")
            raise ImportError("Please install this package with the 'ai' extra.")
        
        self.openai_client: OpenAI = OpenAI(api_key=openai_api_key)
        self.processor: BaseProcessor = processor

    def extract_validation_info(self) -> str:
        """
        Pull validation information from the validators.

        Returns:
            A string containing formatted validation information.
        """
        log("trace", "Extracting validation information")
        def _remove_keys(vd: dict) -> dict:
            """Remove instance variables from the dictionary that are API creds."""
            return {k: v for k, v in vd.items() if not k.endswith("_key")}

        def _format_validator_info(validator: BaseValidator) -> str:
            """Format the information for a single validator."""
            doc = validator.__class__.__doc__ or ""
            return (
                f"- {validator.__class__.__name__}: {doc.strip()}\n"
                f"\tArgs: {_remove_keys(validator.__dict__)}"
            )

        def _get_validators_info(validators: list[BaseValidator]) -> str:
            """Get formatted information for a list of validators."""
            return "\n".join(_format_validator_info(v) for v in validators)

        all_priorities: list[int] = sorted(
            (v.priority for v in self.processor.validators),
            reverse=True
        )
        descending_priorities: list[int] = sorted(set(all_priorities), reverse=True)

        validation_info: str = (
            "Validators by priority (lower number means a higher priority):\n\n"
        )
        for priority in descending_priorities:
            validation_info += (
                f"Priority {priority}:\n"
                f"{_get_validators_info(
                    self.processor.validators_with_priority(priority)
                )}\n"
            )
            validation_info += "\n"

        log("trace", f"Extracted validation info:\n{validation_info}")
        return validation_info.strip()

    def _analyze(self, pii_md5s: list[MD5WithPII]) -> str:
        """
        Internal method to analyze the list of MD5s with PII and generate insights using an LLM.

        Args:
            pii_md5s: List of MD5 hashes with associated PII data.

        Returns:
            Generated insights as a string.
        """
        log("debug", f"Starting analysis for {len(pii_md5s)} MD5s")
        validation_info = self.extract_validation_info()
        
        csv_data, name_mappings = CSVStringFormatterRedacted().deliver(pii_md5s)     # changed from CSVStringFormatter to CSVStringFormatterRedacted               
        log("trace", f"CSV data prepared, length: {len(csv_data)}")
        
        @retry_with_backoff()
        def generate_insights():
            return self.openai_client.beta.chat.completions.parse(
                model="gpt-4o-2024-08-06",
                messages=[
                    {
                        "role": "system",
                        "content": VALIDATOR_PROMPT
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Validations:\n\n{validation_info}\n\n"
                            f"Leads:\n\n{csv_data}"
                        )
                    }
                ],
                max_tokens=4095,
                temperature=1,
                top_p=1,
                frequency_penalty=0,
                presence_penalty=0,
                response_format=ValidatedLeadInsights
            )

        try:
            result = generate_insights()
            lead_insights: ValidatedLeadInsights | None = result.choices[0].message.parsed
        except (self._OpenAI_Error, ValidationError) as e:
            log("error", f"Failed to generate insights after retries. Error: {e}")
            return "Failed to generate insights. Please try again later."

        if not lead_insights:
            log("error", "OpenAI response did not contain valid insights.")
            return "No insights on these leads at the moment."

        log("info", f"Generated {len(lead_insights.insights)} insights")
        log("trace", f"Thoughts from OpenAI: {lead_insights.thoughts}")
        log("trace", f"Validation insight: {lead_insights.validation_insight}")

        for i, insight in enumerate(lead_insights.insights, start=1):
            log("trace", f"Insight {i}: {insight}")

        processed_insights: list[str] = [
            f"{i+1}. {insight}" for i, insight in enumerate(lead_insights.insights)
        ]

        total_str: str = "\n".join(processed_insights)
        
        log("trace", f"Initial insights string:\n{total_str}")
        log("trace", f"Name mappings: {name_mappings}")
        # Replace fake names with real names if present in the insights
        for (fake_first, fake_last), (real_first, real_last) in name_mappings.items(): 
            total_str = total_str.replace(fake_first, real_first)
            total_str = total_str.replace(fake_last, real_last)
        log("trace", f"Final insights string after replacements:\n{total_str}")

        if lead_insights.validation_insight:
            total_str = f"On validation: {lead_insights.validation_insight}\n\n{total_str}"

        log("debug", f"Final insights with validation:\n{total_str}")
        return total_str
