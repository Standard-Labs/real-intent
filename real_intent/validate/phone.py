"""Validate phone numbers using numverify."""
import requests

from concurrent.futures import ThreadPoolExecutor
import time
import random

from real_intent.schemas import MD5WithPII
from real_intent.validate.base import BaseValidator
from real_intent.internal_logging import log


class PhoneValidator(BaseValidator):
    """Remove invalid US phone numbers based on format and Numverify API validation."""

    def __init__(self, numverify_key: str, max_threads: int = 10) -> None:
        """Initialize with numverify key."""
        self.api_key: str = numverify_key
        self.max_threads: int = max_threads

    def _validate_phone(self, phone: str) -> bool:
        """Validate a US phone number with numverify."""
        phone = str(phone)
        if phone.startswith("+1"):
            phone = phone[2:]
        
        if len(phone) == 11 and phone.startswith("1"):
            phone = phone[1:]
        
        if len(phone) != 10:
            return False
        
        response = requests.get(
            "https://apilayer.net/api/validate",
            params={
                "access_key": self.api_key,
                "number": phone,
                "country_code": "US"
            }
        )

        response.raise_for_status()
        response_json = response.json()

        # Handle errors
        if not response_json["success"]:
            if "error" in response_json and response_json["error"]["code"] == 313:
                log("warn", f"Numverify hit a (handled) snag and is marking this number invalid. {response_json}")
                return False

            log("error", f"Failed to validate phone number {phone} with numverify: {response_json}")
            raise ValueError(f"Failed to validate phone number {phone} with numverify: {response_json}")

        # Handle unexpected responses
        if "valid" not in response_json:
            log("error", f"Unexpected response from numverify: {response_json}")
            raise ValueError(f"Unexpected response from numverify: {response_json}")

        # Handle valid responses
        return response_json["valid"]
    
    def _validate_with_retry(self, phone: str) -> bool:
        """Retry the validation if it fails."""
        for _ in range(3):
            try:
                return self._validate_phone(phone)
            except requests.RequestException as e:
                time.sleep(random.uniform(3, 5))

        log("error", f"All validation attempts failed for phone {phone}")
        raise e  # re-raise the last exception

    def _validate(self, md5s: list[MD5WithPII]) -> list[MD5WithPII]:
        """Remove any phone numbers that are not considered valid."""
        # Extract all the phone numbers
        all_phones: list[str] = []
        for md5 in md5s:
            all_phones.extend([phone.phone for phone in md5.pii.mobile_phones])

        # Validate all the phone numbers
        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            valid_phones_idx: list[bool] = list(
                executor.map(self._validate_with_retry, all_phones)
            )

        # Extract valid phone numbers
        valid_phones: list[str] = [
            phone for phone, is_valid in zip(all_phones, valid_phones_idx) if is_valid
        ]

        # Remove invalid phone numbers from MD5s
        for md5 in md5s:
            md5.pii.mobile_phones = [
                phone for phone in md5.pii.mobile_phones if phone.phone in valid_phones
            ]

        return md5s


class HasPhoneValidator(BaseValidator):
    """
    Remove leads without a phone number.

    Use after PhoneValidator to ensure leads have valid phone numbers.
    """

    def _validate(self, md5s: list[MD5WithPII]) -> list[MD5WithPII]:
        """Remove leads without a phone number."""
        return [md5 for md5 in md5s if md5.pii.mobile_phones]


class DNCValidator(BaseValidator):
    """
    Remove leads based on Do Not Call (DNC) status.

    In normal mode:
    - Removes leads with primary phone on DNC list.
    - Keeps leads without phones.

    In strict mode:
    - Removes leads if ANY phone number is on the DNC list.
    - Keeps leads only if ALL phone numbers are not on the DNC list.
    - Keeps leads without phones.
    """

    def __init__(self, strict_mode: bool = False):
        self.strict_mode = strict_mode

    def _validate(self, md5s: list[MD5WithPII]) -> list[MD5WithPII]:
        """
        Remove leads based on DNC status.

        Returns:
            list[MD5WithPII]: Filtered list of leads based on DNC status.
        """
        if self.strict_mode:
            return [
                md5 for md5 in md5s
                if not md5.pii.mobile_phones or
                all(not phone.do_not_call for phone in md5.pii.mobile_phones)
            ]
        else:
            return [
                md5 for md5 in md5s
                if not md5.pii.mobile_phones or not md5.pii.mobile_phones[0].do_not_call
            ]


class DNCPhoneRemover(BaseValidator):
    """
    Removes phone numbers on the DNC list in-place.
    Does not remove leads, simply removes phone numbers from leads.
    """

    def _validate(self, md5s: list[MD5WithPII]) -> list[MD5WithPII]:
        """
        Remove phone numbers on the DNC list.

        Args:
            md5s (list[MD5WithPII]): List of MD5WithPII objects to remove phone numbers from.

        Returns:
            list[MD5WithPII]: List of MD5WithPII objects with DNC phone numbers removed.
        """
        for md5 in md5s:
            md5.pii.mobile_phones = [
                phone for phone in md5.pii.mobile_phones if not phone.do_not_call
            ]

        return md5s


class CallableValidator(BaseValidator):
    """Remove leads without a phone or with primary phone on DNC list."""

    def __init__(
            self, 
            phone_validator: PhoneValidator | None = None, 
            dnc_validator: DNCValidator | None = None
        ):
        self.phone_validator = phone_validator or HasPhoneValidator()
        self.dnc_validator = dnc_validator or DNCValidator()

    def _validate(self, md5s: list[MD5WithPII]) -> list[MD5WithPII]:
        """Remove leads without a phone number or on the DNC list."""
        return self.dnc_validator.validate(self.phone_validator.validate(md5s))
