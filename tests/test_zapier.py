import pytest
from real_intent.deliver.zapier import ZapierDeliverer
from real_intent.schemas import PII, MD5WithPII
from datetime import datetime


@pytest.fixture
def generate_md5withpii():
    def _generate(seed: int, md5: str, sentences: list[str]):
        pii = PII.create_fake(seed=seed)
        return MD5WithPII(
            md5=md5,
            sentences=sentences,
            pii=pii
        )
    return _generate


def test_zapier_deliverer(generate_md5withpii):
    """ Test to mimic how the deliverer will be implemented """

    test1 = generate_md5withpii(seed=55, md5="123", sentences=[
        "test sentence for first md5 123", 
        "another test sentence for first md5 123", 
        "third test sentence for first md5 123", 
        "fourth test sentence for first md5 123"
    ])
    
    test2 = generate_md5withpii(seed=66, md5="456", sentences=[
        "sentence for second md5 456", 
        "sentence for second md5 456",
        "another sentence for second md5 456"
    ])
    
    test3 = generate_md5withpii(seed=77, md5="789", sentences=[
        "sentence for third md5 789"
    ])
        
    insights = {
        "123": "Insight for first md5 123",
        "789": "Insight for third md5 789",
        "456": "Insight for second md5 456"
    }

    md5_list = [test1, test2, test3]

    # working webhook urls, can manually check the data if it was delivered in [Google Sheets, WiseAgent]
    webhook_urls = [
        "https://hooks.zapier.com/hooks/standard/21128362/d382d71573254c1693fdf743d80b5bd9/", 
        "https://hooks.zapier.com/hooks/standard/21128362/f0fa4b54f70a48efaf19ff32e7d09b3d/"
    ]

    deliverer = ZapierDeliverer(webhook_urls=webhook_urls, per_lead_insights=insights)

    response = deliverer.deliver(md5_list)

    # will return False if one of the hooks above unsubscribes aka turned off/deleted. Even if it resubscribes,
    # the webhook url will be different so it will still return False, Can remove this test if it is not needed.
    assert response == True


def test_format(generate_md5withpii):
    """ Test the formatting of the data """

    test1: MD5WithPII = generate_md5withpii(seed=55, md5="123", sentences=[
        "test sentence for first md5 123", 
    ])
    
    insights: dict[str, str] = {
        "123": "Insight for first md5 123"
    }

    md5_list = [test1]

    deliverer = ZapierDeliverer(webhook_urls=[], per_lead_insights=insights)
    formatted_data = deliverer._format(md5_list)

    expected_data = [{
        "md5": "123",
        "pii": {key: (str(value) if value is not None else None) for key, value in test1.pii.as_lead_export().items()},
        "insight": "Insight for first md5 123",
        "sentences": "test sentence for first md5 123", 
        "date_delivered": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }]

    assert formatted_data[0]["md5"] == expected_data[0]["md5"]
    assert formatted_data[0]["pii"] == expected_data[0]["pii"]
    assert formatted_data[0]["insight"] == expected_data[0]["insight"]
    assert formatted_data[0]["sentences"] == expected_data[0]["sentences"]
    assert formatted_data[0]["date_delivered"].startswith(datetime.now().strftime("%Y-%m-%d"))

