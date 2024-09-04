import os

import pytest
from dotenv import load_dotenv

from real_intent.analyze.base import BaseAnalyzer
from real_intent.analyze.insights import OpenAIInsightsGenerator, ValidatedInsightsGenerator
from real_intent.schemas import MD5WithPII, PII

from real_intent.process.fill import FillProcessor
from real_intent.validate.simple import SamePersonValidator
from real_intent.validate.pii import MNWValidator


# Load environment variables
load_dotenv()


class TestAnalyzer(BaseAnalyzer):
    def _analyze(self, md5s: list[MD5WithPII]) -> str:
        return f"Analyzed {len(md5s)} MD5s"


def create_test_pii() -> PII:
    return PII.from_api_dict({
        "Id": "test_id",
        "First_Name": "John",
        "Last_Name": "Doe",
        "Address": "123 Test St",
        "City": "Test City",
        "State": "TS",
        "Zip": "12345",
        "Email_Array": ["john@example.com"],
        "Gender": "Male",
        "Age": "30",
        "Children_HH": "2",
        "Credit_Range": "Good",
        "Home_Owner": "Yes",
        "Income_HH": "100000-150000",
        "Net_Worth_HH": "500000-1000000",
        "Marital_Status": "Married",
        "Occupation_Detail": "Engineer",
        "Veteran_HH": "0"
    })


def test_base_analyzer() -> None:
    analyzer = TestAnalyzer()
    md5s = [
        MD5WithPII(md5="123", sentences=["test"], pii=create_test_pii()),
        MD5WithPII(md5="456", sentences=["test"], pii=create_test_pii())
    ]
    result = analyzer.analyze(md5s)
    assert result == "Analyzed 2 MD5s"


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not found")
def test_openai_insights_generator() -> None:
    api_key = os.getenv("OPENAI_API_KEY")
    generator = OpenAIInsightsGenerator(api_key)
    md5s = [
        MD5WithPII(md5="123", sentences=["Interested in buying a new car"], pii=create_test_pii()),
        MD5WithPII(md5="456", sentences=["Looking for auto insurance"], pii=create_test_pii())
    ]
    result = generator.analyze(md5s)
    assert isinstance(result, str)
    assert len(result.split("\n")) >= 2  # Expecting at least two insights


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not found")
def test_validated_insights_generator(bigdbm_client) -> None:
    api_key = os.getenv("OPENAI_API_KEY")

    processor = FillProcessor(bigdbm_client)
    processor.add_validator(SamePersonValidator())
    processor.add_validator(MNWValidator(), priority=2)

    generator = ValidatedInsightsGenerator(api_key, processor)
    md5s = [
        MD5WithPII(md5="123", sentences=["Interested in buying a new car"], pii=create_test_pii()),
        MD5WithPII(md5="456", sentences=["Looking for auto insurance"], pii=create_test_pii())
    ]
    result = generator.analyze(md5s)
    assert isinstance(result, str)
    assert "On validation:" in result
    assert len(result.split("\n")) >= 3  # Expecting validation insight and at least two regular insights
