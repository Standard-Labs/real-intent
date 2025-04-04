import os
import pytest
from dotenv import load_dotenv

from real_intent.schemas import MD5WithPII, PII, MobilePhone
from real_intent.validate.email import EmailValidator, HasEmailValidator
from real_intent.validate.phone import PhoneValidator, DNCValidator, DNCPhoneRemover
from real_intent.validate.pii import RemoveOccupationsValidator
from real_intent.validate.simple import ExcludeZipCodeValidator


# Load environment variables from .env file
load_dotenv()


def create_md5_with_pii(md5: str, emails: list[str], phones: list[str], sentences: list[str] | None = None) -> MD5WithPII:
    # Default to a single test sentence if none are forced
    if sentences is None:
        sentences = ["test sentence"]
    
    # Create a base PII object with fake data
    pii = PII.create_fake(seed=42)  # Use consistent seed for reproducibility
    
    # Override with test-specific values
    pii.emails = emails
    pii.mobile_phones = [MobilePhone(phone=phone, do_not_call=False) for phone in phones]
    
    return MD5WithPII(md5=md5, sentences=sentences, pii=pii)


def test_email_validator() -> None:
    million_verifier_key = os.getenv("MILLION_VERIFIER_KEY")
    if not million_verifier_key:
        pytest.skip("MILLION_VERIFIER_KEY not found in .env file")
    
    validator = EmailValidator(million_verifier_key)
    
    real_emails = [
        "aaron@standarddao.finance"
    ]
    fake_emails = [
        "rfisascasdcabsdasdcabsjhdcher@yahoo.com",
        "dju123123123123123pedal@yahoo.com",
        "khris678asdc678asdc@aol.com"
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


def test_dnc_phone_remover() -> None:
    remover = DNCPhoneRemover()
    
    md5s = [
        create_md5_with_pii("123", [], ["1234567890", "9876543210"]),  # Both not on DNC
        create_md5_with_pii("456", [], ["1112223333", "4445556666"]),  # First on DNC, second not
        create_md5_with_pii("789", [], ["7778889999", "1231231234"]),  # Both on DNC
        create_md5_with_pii("101", [], [])  # No phones
    ]
    
    # Set DNC status
    md5s[1].pii.mobile_phones[0].do_not_call = True
    md5s[2].pii.mobile_phones[0].do_not_call = True
    md5s[2].pii.mobile_phones[1].do_not_call = True
    
    result = remover.validate(md5s)
    
    assert len(result) == 4  # All MD5s should be kept
    
    # Check MD5 with both phones not on DNC
    assert len(result[0].pii.mobile_phones) == 2
    assert result[0].pii.mobile_phones[0].phone == "1234567890"
    assert result[0].pii.mobile_phones[1].phone == "9876543210"
    
    # Check MD5 with one phone on DNC
    assert len(result[1].pii.mobile_phones) == 1
    assert result[1].pii.mobile_phones[0].phone == "4445556666"
    
    # Check MD5 with both phones on DNC
    assert len(result[2].pii.mobile_phones) == 0
    
    # Check MD5 with no phones
    assert len(result[3].pii.mobile_phones) == 0


def test_sentence_count() -> None:
    # Check for different sentence calculation methods
    md5 = create_md5_with_pii("123", [], [], sentences=["sentence1", "sentence2", "sentence1", "sentence3"])
    assert md5.total_sentence_count == 4
    assert md5.unique_sentence_count == 3

    # Check for single sentence
    md5_single = create_md5_with_pii("456", [], [], sentences=["single sentence"])
    assert md5_single.total_sentence_count == 1
    assert md5_single.unique_sentence_count == 1

    # Check for empty sentences
    md5_empty = create_md5_with_pii("789", [], [], sentences=[])
    assert md5_empty.total_sentence_count == 0
    assert md5_empty.unique_sentence_count == 0


def test_remove_occupations_validator() -> None:
    piis = [
        create_md5_with_pii("123", [], ["1234567890"], sentences=["sentence1"]),
        create_md5_with_pii("456", [], ["9876543210"], sentences=["sentence2"]),
        create_md5_with_pii("789", [], ["5556667777"], sentences=["sentence3"]),
        create_md5_with_pii("101", [], ["9998887777"], sentences=["sentence4"])
    ]

    # Set occupations
    piis[0].pii.occupation = "Bad Occupation"

    # Initialize validator
    validator = RemoveOccupationsValidator("Bad Occupation")

    # Validate
    result = validator.validate(piis)

    # Check results
    assert len(result) == 3


def test_exclude_zip_code_validator() -> None:
    # Create test data with different zip codes
    md5s = [
        create_md5_with_pii("123", [], []),  # Will set zip code below
        create_md5_with_pii("456", [], []),  # Will set zip code below
        create_md5_with_pii("789", [], []),  # Will set zip code below
        create_md5_with_pii("101", [], [])   # Will set zip code below
    ]
    
    # Set zip codes
    md5s[0].pii.zip_code = "10001"  # NYC - should be excluded
    md5s[1].pii.zip_code = "90210"  # Beverly Hills - should be kept
    md5s[2].pii.zip_code = "60601"  # Chicago - should be kept
    md5s[3].pii.zip_code = "33139"  # Miami Beach - should be excluded
    
    # Initialize validator with zip codes to exclude
    excluded_zip_codes = ["10001", "33139"]
    validator = ExcludeZipCodeValidator(excluded_zip_codes)
    
    # Validate
    result = validator.validate(md5s)
    
    # Check results
    assert len(result) == 2
    assert result[0].md5 == "456"  # Beverly Hills zip should be kept
    assert result[1].md5 == "789"  # Chicago zip should be kept
    assert all(md5.md5 != "123" for md5 in result)  # NYC zip should be excluded
    assert all(md5.md5 != "101" for md5 in result)  # Miami Beach zip should be excluded
    
    # Check that the zip codes in the result are the ones we expect to keep
    assert result[0].pii.zip_code == "90210"
    assert result[1].pii.zip_code == "60601"
