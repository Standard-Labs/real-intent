import os
import pytest
from dotenv import load_dotenv

from real_intent.schemas import MD5WithPII, PII, MobilePhone
from real_intent.validate.email import EmailValidator, HasEmailValidator
from real_intent.validate.phone import PhoneValidator, DNCValidator


# Load environment variables from .env file
load_dotenv()


def create_md5_with_pii(md5: str, emails: list[str], phones: list[str]) -> MD5WithPII:
    pii = PII(
                Id="test_id",
                First_Name="Tuna",
                Last_Name="Sandwich",
                Address="123 Test St",
                City="Test City",
                State="TS",
                Zip="12345",
                Zip4="2224",
                Fips_State_Code="01",
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
                Email_Array=["tunasandwich@gmail.com"],
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
                Health_Beauty_Products="Yes",
                Cosmetics="Yes",
                Jewelry="Yes",
                Investment_Type="Stocks",
                Investments="Yes",
                Pet_Owner="No",
                Pets_Affinity="Cats",
                Health_Affinity="Fitness",
                Diet_Affinity="Low Carb",
                Fitness_Affinity="Gym",
                Outdoors_Affinity="Hiking",
                Boating_Sailing_Affinity="Yes",
                Camping_Hiking_Climbing_Affinity="Yes",
                Fishing_Affinity="Yes",
                Hunting_Affinity="Yes",
                Aerobics="Yes",
                NASCAR="Yes",
                Scuba="Yes",
                Weight_Lifting="Yes",
                Healthy_Living_Interest="Yes",
                Motor_Racing="Yes",
                Travel_Foreign="Yes",
                Self_Improvement="Yes",
                Walking="Yes",
                Fitness="Yes",
                Ethnicity_Detail="Caucasian",
                Ethnic_Group="Caucasian",
    )
    
    pii.mobile_phones = [MobilePhone(phone=phone, do_not_call=False) for phone in phones]
    
    return MD5WithPII(md5=md5, sentences=["test sentence"], pii=pii)


def test_email_validator() -> None:
    million_verifier_key = os.getenv("MILLION_VERIFIER_KEY")
    if not million_verifier_key:
        pytest.skip("MILLION_VERIFIER_KEY not found in .env file")
    
    validator = EmailValidator(million_verifier_key)
    
    real_emails = [
        "matsn@outlook.com",
        "dogdude@hotmail.com",
        "harryh@live.com"
    ]
    fake_emails = [
        "rfisher@yahoo.com",
        "djupedal@yahoo.com",
        "khris@aol.com"
    ]
    
    md5s = [
        create_md5_with_pii("123", real_emails + fake_emails, []),
    ]
    
    result = validator.validate(md5s)
    
    assert len(result) == 1
    validated_emails = result[0].pii.emails
    
    assert any(email in validated_emails for email in real_emails), "No real emails were validated"
    assert any(email not in validated_emails for email in fake_emails), "All fake emails were validated"
    assert all(email in validated_emails for email in real_emails), "Not all real emails were validated"
    assert all(email not in validated_emails for email in fake_emails), "Some fake emails were validated"


def test_has_email_validator() -> None:
    validator = HasEmailValidator()
    
    md5s = [
        create_md5_with_pii("123", ["valid@example.com"], []),
        create_md5_with_pii("456", [], []),
        create_md5_with_pii("789", ["another@example.com"], [])
    ]
    
    result = validator.validate(md5s)
    
    assert len(result) == 2
    assert result[0].md5 == "123"
    assert result[1].md5 == "789"


def test_phone_validator() -> None:
    numverify_key = os.getenv("NUMVERIFY_KEY")
    if not numverify_key:
        pytest.skip("NUMVERIFY_KEY not found in .env file")
    
    validator = PhoneValidator(numverify_key=numverify_key)
    
    real_phones = [
        "18002752273",
        "18006427676",
        "18882804331"
    ]
    fake_phones = [
        "17489550914",
        "12573425053",
        "12889061135"
    ]
    
    md5s = [
        create_md5_with_pii("123", [], real_phones + fake_phones),
    ]
    
    result = validator.validate(md5s)
    
    assert len(result) == 1
    validated_phones = [phone.phone for phone in result[0].pii.mobile_phones]
    
    assert any(phone in validated_phones for phone in real_phones), "No real phones were validated"
    assert any(phone not in validated_phones for phone in fake_phones), "All fake phones were validated"
    assert all(phone in validated_phones for phone in real_phones), "Not all real phones were validated"
    assert all(phone not in validated_phones for phone in fake_phones), "Some fake phones were validated"


def test_dnc_validator() -> None:
    # Test normal mode
    validator_normal = DNCValidator(strict_mode=False)
    
    md5s = [
        create_md5_with_pii("123", [], ["1234567890"]),  # Not on DNC list
        create_md5_with_pii("456", [], []),  # No phone
        create_md5_with_pii("789", [], ["9876543210", "1112223333"]),  # Primary on DNC, secondary not
        create_md5_with_pii("101", [], ["5556667777", "9998887777"])  # Primary not on DNC, secondary on DNC
    ]
    
    # Set DNC status
    md5s[2].pii.mobile_phones[0].do_not_call = True
    md5s[3].pii.mobile_phones[1].do_not_call = True
    
    result_normal = validator_normal.validate(md5s)
    
    assert len(result_normal) == 3
    assert result_normal[0].md5 == "123"  # Keep: has phone, not on DNC
    assert result_normal[1].md5 == "456"  # Keep: no phone
    assert result_normal[2].md5 == "101"  # Keep: primary not on DNC
    assert all(md5.md5 != "789" for md5 in result_normal)  # Remove: primary on DNC

    # Test strict mode
    validator_strict = DNCValidator(strict_mode=True)
    
    result_strict = validator_strict.validate(md5s)
    
    assert len(result_strict) == 2
    assert result_strict[0].md5 == "123"  # Keep: has phone, not on DNC
    assert result_strict[1].md5 == "456"  # Keep: no phone
    assert all(md5.md5 != "789" for md5 in result_strict)  # Remove: has DNC phone
    assert all(md5.md5 != "101" for md5 in result_strict)  # Remove: has DNC phone (secondary)
