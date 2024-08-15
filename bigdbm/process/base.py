"""Base processor."""
from abc import ABC, abstractmethod
from typing import Self

from bigdbm.client import BigDBMClient
from bigdbm.schemas import IABJob, MD5WithPII
from bigdbm.validate.base import BaseValidator
from bigdbm.validate.simple import ContactableValidator


DEFAULT_VALIDATORS: list[BaseValidator] = [
    ContactableValidator()
]


class BaseProcessor(ABC):
    """
    Base processor, takes an IAB job and finishes with a list of MD5s with PII.
    All implementations must follow the `.process()` schema.

    The MD5s with PII are the input for deliverers.

    Comes with an __init__ that takes a BigDBM client. If overriding the __init__
    for some reason, be sure to super() and make sure self.client is defined.

    When working with validators, method chaining is possible as an instance of self
    is returned for `.add_validator` and `.clear_validators`.
    Ex: `FillProcessor(client).add_validator(validator).process(job)`
    """

    def __init__(self, bigdbm_client: BigDBMClient) -> None:
        """Initialize with a client."""
        self.client = bigdbm_client
        self.required_validators: list[BaseValidator] = []
        self.fallback_validators: list[BaseValidator] = []

    @property
    def validators(self) -> list[BaseValidator]:
        """Return all validators."""
        return self.required_validators + self.fallback_validators

    def clear_validators(self) -> Self:
        """Remove all validators from the processor."""
        self.required_validators = []
        self.fallback_validators = []
        return self

    def add_validator(self, validator: BaseValidator, allow_fallback: bool = False) -> Self:
        """
        Add a validator instance to the processor's validators.

        Args:
            validator: A BaseValidator instance.
            allow_fallback: If True, the validator will be removed from validation if
                not enough leads are found post-validation. Note that the Processor
                must implement this behavior.
        """
        if not isinstance(validator, BaseValidator):
            raise TypeError("You must pass in a valid BaseValidator instance.")

        if allow_fallback:
            self.fallback_validators.append(validator)
        else:
            self.required_validators.append(validator)

        return self

    def add_default_validators(self, allow_fallback: bool = False) -> Self:
        """
        Insert the default validators into the processor.

        Args:
            allow_fallback: If True, the default validators will be removed from 
                validation if not enough leads are found post-validation. Note that the 
                Processor must implement this behavior.
        """
        for validator in DEFAULT_VALIDATORS:
            self.add_validator(validator, allow_fallback=allow_fallback)

        return self

    @abstractmethod
    def process(self, iab_job: IABJob) -> list[MD5WithPII]:
        """Take an IABJob and process it into a list of MD5s with PII."""
