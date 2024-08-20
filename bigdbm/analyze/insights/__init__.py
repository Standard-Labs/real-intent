"""Use an LLM to generate insights from PII data."""
from pydantic import BaseModel, Field

from bigdbm.analyze.base import BaseAnalyzer
from bigdbm.schemas import MD5WithPII

from bigdbm.analyze.insights.prompt import SYSTEM_PROMPT
from bigdbm.format.csv import CSVStringFormatter


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
            "marketing strategies and personalized outreach efforts."
        )
    )


class OpenAIInsightGenerator(BaseAnalyzer):
    """Generates insights from PII data using OpenAI."""

    def __init__(self, openai_api_key: str):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("Please install the openai package to use this analyzer.")
        
        self.openai_client = OpenAI(api_key=openai_api_key)

    def analyze(self, pii_md5s: list[MD5WithPII]) -> str:
        """
        Analyze the list of MD5s with PII and generate insights using an LLM.

        Args:
            pii_md5s (list[MD5WithPII]): List of MD5 hashes with associated PII data.

        Returns:
            str: Generated insights as a string.
        """
        result = self.openai_client.beta.chat.completions.parse(
            model="gpt-4o-2024-08-06",
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": CSVStringFormatter().format_md5s(pii_md5s)
                }
            ],
            max_tokens=4095,
            temperature=1,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0,
            response_format=LeadInsights
        )

        lead_insights: LeadInsights | None = result.choices[0].message.parsed

        if not lead_insights:
            return "No insights on these leads at the moment."

        return "\n".join(lead_insights.insights)