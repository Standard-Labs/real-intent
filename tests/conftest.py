"""Client, etc."""
import pytest

import os
from dotenv import load_dotenv
import random
import string

from real_intent.client import BigDBMClient
from real_intent.schemas import MD5WithPII, PII, MobilePhone, Gender


# Load env
load_dotenv()


# Configure logfire if write token is given
if os.getenv("LOGFIRE_WRITE_TOKEN"):
    try:
        import logfire
    except ImportError:
        pass
    else:
        logfire.configure(token=os.getenv("LOGFIRE_WRITE_TOKEN"), send_to_logfire=True)


@pytest.fixture(scope="session")
def bigdbm_client() -> BigDBMClient:
    """Create a BigDBM client object."""
    client_id: str = os.environ.get("CLIENT_ID", "")
    client_secret: str = os.environ.get("CLIENT_SECRET", "")

    if not (client_id and client_secret):
        raise ValueError("Need CLIENT_ID and CLIENT_SECRET variables to run tests.")

    return BigDBMClient(client_id, client_secret)


def generate_random_name(length=6):
    """Generate a random name of given length."""
    return ''.join(random.choice(string.ascii_lowercase) for _ in range(length)).capitalize()


@pytest.fixture(scope="session")
def sample_pii_md5s():
    first_name = generate_random_name()
    last_name = generate_random_name()
    email = f"{first_name.lower()}.{last_name.lower()}@example.com"
    return [
        MD5WithPII(
            md5="1234567890abcdef",
            sentences=["test sentence"],
            pii=PII(
                Id="test_id",
                First_Name=first_name,
                Last_Name=last_name,
                Address="123 Test St",
                City="Test City",
                State="TS",
                Zip="12345",
                Zip4="2224",
                Fips_State_Code="001",
                Fips_County_Code="002",
                County_Name="Columbia",
                Latitude="34.1234",
                Longitude="-87.1234",
                Address_Type="Residential",
                Cbsa="12345",
                Census_Tract="123456",
                Census_Block_Group="1",
                Census_Block="1",
                Gender=Gender.MALE,
                SCF="123",
                DMA="333",
                MSA="222",
                Congressional_District="7",
                HeadOfHousehold="Yes",
                Birth_Month_and_Year="01/1990",
                Age="45",
                Prop_Type="Single Family",
                Email_Array=[email],
                mobile_phones=[MobilePhone(phone="1234567890", do_not_call=False)],
                Children_HH="2",
                Credit_Range="Good",
                Income_HH="100000-150000",
                Net_Worth_HH="500000-1000000",
                Home_Owner="Yes",
                Marital_Status="Married",
                Occupation_Detail="Engineer",
                Median_Home_Value="200000",
                Education="Bachelors",
                Length_of_Residence="5",
                Num_Adults_HH="2",
                Political_Party="Republican",
                Health_Beauty_Products="1",
                Cosmetics="1",
                Jewelry="1",
                Investment_Type="1",
                Investments="1",
                Pet_Owner="1",
                Pets_Affinity="1",
                Health_Affinity="1",
                Diet_Affinity="1",
                Fitness_Affinity="1",
                Outdoors_Affinity="1",
                Boating_Sailing_Affinity="1",
                Camping_Hiking_Climbing_Affinity="1",
                Fishing_Affinity="1",
                Hunting_Affinity="1",
                Aerobics="1",
                NASCAR="1",
                Scuba="1",
                Weight_Lifting="1",
                Healthy_Living_Interest="1",
                Motor_Racing="1",
                Travel_Foreign="1",
                Self_Improvement="1",
                Walking="1",
                Fitness="1",
                Ethnicity_Detail="Caucasian",
                Ethnic_Group="Caucasian",
            )
        )
    ]
