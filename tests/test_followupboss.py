"""Test the Follow Up Boss deliverer."""
import pytest

import os
from dotenv import load_dotenv
import string
import random

from real_intent.deliver.followupboss import FollowUpBossDeliverer
from real_intent.deliver.utils import InvalidCRMCredentialsError
from real_intent.deliver.followupboss.ai_fields import AIFollowUpBossDeliverer, InvalidOpenAICredentialsError


# Load environment variables from .env file
load_dotenv()


@pytest.fixture
def api_key():
    return os.getenv('FOLLOWUPBOSS_API_KEY')


@pytest.fixture
def system():
    return os.getenv('FOLLOWUPBOSS_SYSTEM')


@pytest.fixture
def system_key():
    return os.getenv('FOLLOWUPBOSS_SYSTEM_KEY')


@pytest.fixture
def openai_api_key():
    return os.getenv('OPENAI_API_KEY')


@pytest.fixture
def followupboss_deliverer(api_key, system, system_key):
    return FollowUpBossDeliverer(api_key, system, system_key)


@pytest.fixture
def ai_followupboss_deliverer(api_key, system, system_key, openai_api_key):
    return AIFollowUpBossDeliverer(api_key, system, system_key, openai_api_key)


@pytest.mark.skipif(not os.getenv("FOLLOWUPBOSS_API_KEY"), reason="FUB API key not found")
def test_followupboss_deliverer_success(followupboss_deliverer, sample_pii_md5s):
    """
    Test the successful delivery of PII data using the FollowUpBossDeliverer, including tag functionality.

    This test verifies that:
    1. The deliverer successfully sends the PII data to Follow Up Boss.
    2. The response contains the expected data (id, first name, last name, email, phone).
    3. The delivered data matches the input sample PII data.
    4. The tags are correctly included in the delivered data.

    Args:
        followupboss_deliverer (FollowUpBossDeliverer): The FollowUpBossDeliverer instance.
        sample_pii_md5s (list): A list containing a sample MD5WithPII object.

    Raises:
        AssertionError: If any of the assertions fail, indicating that the delivery was not successful,
                        the returned data does not match the expected values, or the tags are not correctly included.
    """
    # Add tags to the existing deliverer
    tags = ["Test Tag 1", "Test Tag 2"]
    followupboss_deliverer.tags = tags

    # Calculate expected tags based on add_zip_tags setting
    expected_tags = tags.copy()
    if followupboss_deliverer.add_zip_tags and sample_pii_md5s[0].pii.zip_code:
        expected_tags.append(sample_pii_md5s[0].pii.zip_code)

    # Test that tags are included in the prepared event data
    event_data = followupboss_deliverer._prepare_event_data(sample_pii_md5s[0])
    assert "tags" in event_data["person"], "Tags not found in prepared event data"
    assert set(event_data["person"]["tags"]) == set(expected_tags), "Prepared event data does not contain the correct tags"

    # Test delivery and verify tags in the result
    result = followupboss_deliverer.deliver([sample_pii_md5s[0]])

    assert len(result) == 1
    assert "id" in result[0]
    assert result[0]["firstName"] == sample_pii_md5s[0].pii.first_name
    assert result[0]["lastName"] == sample_pii_md5s[0].pii.last_name
    assert any(email["value"] == sample_pii_md5s[0].pii.emails[0] for email in result[0]["emails"])

    # Verify tags in the delivered data
    assert "tags" in result[0], "Tags not found in delivered person data"
    assert set(result[0]["tags"]) == set(expected_tags), "Delivered person data does not contain the correct tags"


@pytest.mark.skipif(not os.getenv("FOLLOWUPBOSS_API_KEY"), reason="FUB API key not found")
def test_prepare_event_data(followupboss_deliverer, sample_pii_md5s):
    """
    Test the _prepare_event_data method of the FollowUpBossDeliverer.

    This test verifies that:
    1. The method correctly prepares the event data from the input PII data.
    2. The prepared event data contains the correct system information.
    3. The person data in the event includes the correct first name, last name, email, and phone number.

    Args:
        followupboss_deliverer (FollowUpBossDeliverer): The FollowUpBossDeliverer instance.
        sample_pii_md5s (list): A list containing a sample MD5WithPII object.

    Raises:
        AssertionError: If any of the assertions fail, indicating that the event data was not prepared correctly
                        or does not contain the expected information.
    """
    event_data = followupboss_deliverer._prepare_event_data(sample_pii_md5s[0])

    assert event_data["system"] == followupboss_deliverer.system
    assert event_data["person"]["firstName"] == sample_pii_md5s[0].pii.first_name
    assert event_data["person"]["lastName"] == sample_pii_md5s[0].pii.last_name
    assert sample_pii_md5s[0].pii.emails[0] in [email["value"] for email in event_data["person"]["emails"]]
    assert event_data["person"]["addresses"] == [{
        "type": "home",
        "street": sample_pii_md5s[0].pii.address,
        "city": sample_pii_md5s[0].pii.city,
        "state": sample_pii_md5s[0].pii.state,
        "code": sample_pii_md5s[0].pii.zip_code
    }]


@pytest.mark.skipif(not os.getenv("FOLLOWUPBOSS_API_KEY") or not os.getenv("OPENAI_API_KEY"), reason="FUB API key or OpenAI API key not found")
def test_ai_followupboss_deliverer_success(ai_followupboss_deliverer, sample_pii_md5s):
    """
    Test the successful delivery of PII data using the AIFollowUpBossDeliverer.

    This test verifies that:
    1. The AI-powered deliverer successfully sends the PII data to Follow Up Boss.
    2. The response contains the expected basic data (id, first name, last name, email, phone).
    3. The AI has added the "Net Worth" custom field to the person data.
    4. The "Net Worth" value is correctly mapped from the PII data.
    5. The AI did not fall back to the non-AI method.

    Args:
        ai_followupboss_deliverer (AIFollowUpBossDeliverer): The AIFollowUpBossDeliverer instance.
        sample_pii_md5s (list): A list containing a sample MD5WithPII object.

    Raises:
        AssertionError: If any of the assertions fail, indicating that the AI-powered delivery was not successful,
            the returned data does not match the expected values, the "Net Worth" field was not added,
            or the AI fell back to the non-AI method.
    """
    result = ai_followupboss_deliverer.deliver(sample_pii_md5s)

    assert len(result) == 1
    assert "id" in result[0]
    assert result[0]["firstName"] == sample_pii_md5s[0].pii.first_name
    assert result[0]["lastName"] == sample_pii_md5s[0].pii.last_name
    assert any(email["value"] == sample_pii_md5s[0].pii.emails[0] for email in result[0]["emails"])

    # Check if the "Net Worth" custom field was added by the AI
    custom_fields = ai_followupboss_deliverer._get_custom_fields()
    event_data = ai_followupboss_deliverer._prepare_event_data(sample_pii_md5s[0])
    
    net_worth_field = next((field for field in custom_fields if field.label == "Net Worth"), None)
    assert net_worth_field is not None, "Net Worth custom field not found"
    
    assert net_worth_field.name in event_data["person"], "Net Worth field not added to person data"
    assert event_data["person"][net_worth_field.name] == sample_pii_md5s[0].pii.household_net_worth, "Net Worth value not correctly mapped"

    # Check that the AI didn't fall back to the non-AI method
    assert len(event_data["person"]) > 4, "AI seems to have fallen back to non-AI method"


@pytest.mark.skipif(
    not os.getenv("FOLLOWUPBOSS_API_KEY")
    or not os.getenv("FOLLOWUPBOSS_SYSTEM")
    or not os.getenv("FOLLOWUPBOSS_SYSTEM_KEY"),
    reason="FUB API keys not found",
)
def test_vanilla_followupboss_credential_validation(api_key, system, system_key):
    # Test valid credentials and ensure that they work correctly
    FollowUpBossDeliverer(api_key, system, system_key)

    # Test invalid credentials and ensure that they don't throw exception
    with pytest.raises(InvalidCRMCredentialsError):
        FollowUpBossDeliverer("invalid_api_key", system, system_key)


@pytest.mark.skipif(
    not os.getenv("FOLLOWUPBOSS_API_KEY")
    or not os.getenv("FOLLOWUPBOSS_SYSTEM")
    or not os.getenv("FOLLOWUPBOSS_SYSTEM_KEY")
    or not os.getenv("OPENAI_API_KEY"),
    reason="FUB API keys or OpenAI API key not found",
)
def test_ai_followupboss_credential_validation(api_key, system, system_key, openai_api_key):
    # Test valid credentials and ensure that they work correctly
    AIFollowUpBossDeliverer(api_key, system, system_key, openai_api_key)

    # Test invalid credentials and ensure that they don't throw exception
    with pytest.raises(InvalidCRMCredentialsError):
        AIFollowUpBossDeliverer("invalid_api_key", system, system_key, openai_api_key)

    # Test OpenAI API key validation
    with pytest.raises(InvalidOpenAICredentialsError):
        AIFollowUpBossDeliverer(api_key, system, system_key, "invalid_openai_api_key")


@pytest.mark.skipif(not os.getenv("FOLLOWUPBOSS_API_KEY"), reason="FUB API key not found")
def test_followupboss_deliverer_perlead_insights(api_key, system, system_key, openai_api_key, sample_pii_md5s):
    per_lead_insights: dict[str, str] = {
        p.md5: "".join(random.choices(string.ascii_letters, k=10)) for p in sample_pii_md5s
    }

    deliverer = AIFollowUpBossDeliverer(
        api_key, 
        system, 
        system_key, 
        openai_api_key, 
        per_lead_insights=per_lead_insights
    )
    response = deliverer.deliver(sample_pii_md5s)

    for person in response:
        assert deliverer._add_note(person["id"], body="Test", subject="Test")


@pytest.mark.skipif(not os.getenv("FOLLOWUPBOSS_API_KEY"), reason="FUB API key not found")
def test_followupboss_deliverer_zip_tags(followupboss_deliverer, sample_pii_md5s):
    """Test that ZIP codes are correctly added as tags when add_zip_tags is True."""
    # Enable ZIP tags (should be True by default)
    followupboss_deliverer.add_zip_tags = True
    
    # Add some regular tags
    regular_tags = ["Test Tag 1", "Test Tag 2"]
    followupboss_deliverer.tags = regular_tags

    # Test that ZIP tags are included in the prepared event data
    event_data = followupboss_deliverer._prepare_event_data(sample_pii_md5s[0])
    assert "tags" in event_data["person"], "Tags not found in prepared event data"
    
    expected_tags = regular_tags + [sample_pii_md5s[0].pii.zip_code]
    assert set(event_data["person"]["tags"]) == set(expected_tags), "ZIP code not added to tags"

    # Test with add_zip_tags disabled
    followupboss_deliverer.add_zip_tags = False
    event_data = followupboss_deliverer._prepare_event_data(sample_pii_md5s[0])
    assert set(event_data["person"]["tags"]) == set(regular_tags), "Tags include ZIP code when add_zip_tags is False"
