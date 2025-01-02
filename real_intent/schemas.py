"""Datatypes for working with the API."""
from pydantic import BaseModel, Field, model_validator, field_validator, ConfigDict

from typing import Any, Optional, Self
from enum import Enum
import random
import string
from datetime import datetime, timedelta

from real_intent.taxonomy import code_to_category


class ConfigDates(BaseModel):
    """Start and end dates as returned by the /config route."""
    start_date: str
    end_date: str


class IABJob(BaseModel):
    """Payload for creating an IAB job."""
    intent_categories: list[str] = Field(
        default_factory=list, description="List of IAB intent categories"
    )
    zips: list[str] = Field(
        default_factory=list, description="List of zip codes"
    )
    keywords: list[str] = Field(
        default_factory=list, description="List of keywords"
    )
    domains: list[str] = Field(
        default_factory=list, description="List of domains"
    )
    n_hems: int

    @model_validator(mode="after")
    def validate_job(self) -> Self:
        """Make sure the job has enough information to run."""
        if all(
            [
                not self.intent_categories,
                not self.keywords,
                not self.domains
            ]
        ):
            raise ValueError(
                "Need at least one of intent categories, keywords, or domains.\n" + str(self.model_dump())
            )

        return self

    def as_payload(self) -> dict[str, str | int]:
        """Convert into dictionary payload."""
        return {
            "IABs": ",".join(self.intent_categories),
            "Zips": ",".join(self.zips),
            "Keywords": ",".join(self.keywords),
            "Domains": ",".join(self.domains),
            "NumberOfHems": self.n_hems
        }


class IntentEvent(BaseModel):
    """
    MD5 intent event as returned by API.
    Timestamp not supported yet.
    """
    md5: str
    sentence: str


class UniqueMD5(BaseModel):
    """
    Unique MD5 with all the associated sentences.

    `sentences` should be defined as whatever comes back from the API.
    Field validation automatically transforms IAB _codes_ into _strings_
    and removes duplicates.
    """
    md5: str
    sentences: list[str]
    raw_sentences: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def transform_iab_codes(self) -> Self:
        """Convert any valid IAB codes into strings and count total sentences."""
        self.raw_sentences = self.sentences
        unique_sentences = list(set(self.sentences))

        for pos, sentence in enumerate(unique_sentences):
            if sentence.isnumeric():
                unique_sentences[pos] = code_to_category(sentence)

        self.sentences = unique_sentences
        return self

    @property
    def unique_sentence_count(self) -> int:
        """Total number of unique sentences."""
        return len(self.sentences)

    @property
    def total_sentence_count(self) -> int:
        """Total number of sentences (non-unique)."""
        return len(self.raw_sentences)
    

class MobilePhone(BaseModel):
    """An individual's phone number."""
    phone: str
    do_not_call: bool


class Gender(str, Enum):
    """Classifications of genders."""
    MALE = "Male"
    FEMALE = "Female"
    UNKNOWN = "Unknown"
    EMPTY = ""


class PII(BaseModel):
    """
    PII in output code 10026 as returned by BigDBM API directly.
    No transformations, only typed data validation.

    Instantiate with `.from_api_dict` to ensure correct pre-processing of 
    mobile phone data.
    """
    model_config = ConfigDict(populate_by_name=True)  # allow instantiating with python var names

    id: str = Field(..., alias="Id", description="BigDBM person ID")
    first_name: str = Field(..., alias="First_Name")
    last_name: str = Field(..., alias="Last_Name")
    address: str = Field(..., alias="Address")
    city: str = Field(..., alias="City")
    # national_consumer_database  # what is this, and what type?
    state: str = Field(..., alias="State")
    zip_code: str = Field(..., alias="Zip")
    zip4: str = Field(..., alias="Zip4")
    fips_state_code: str = Field(..., alias="Fips_State_Code")
    fips_county_code: str = Field(..., alias="Fips_County_Code")
    county_name: str = Field(..., alias="County_Name")
    latitude: Optional[float] = Field(None, alias="Latitude")
    longitude: Optional[float] = Field(None, alias="Longitude")
    address_type: str = Field(..., alias="Address_Type")
    cbsa: str = Field(..., alias="Cbsa")
    census_tract: str = Field(..., alias="Census_Tract")
    census_block_group: int | str = Field(..., alias="Census_Block_Group")
    census_block: str = Field(..., alias="Census_Block")
    gender: Gender = Field(..., alias="Gender")
    scf: str = Field(..., alias="SCF")
    dma: str = Field(..., alias="DMA")
    msa: str = Field(..., alias="MSA")
    congressional_district: str = Field(..., alias="Congressional_District")
    head_of_household: bool | str = Field(..., alias="HeadOfHousehold")
    birth_month_and_year: str = Field(..., alias="Birth_Month_and_Year")
    age: int | str = Field(..., alias="Age")
    prop_type: str = Field(..., alias="Prop_Type")
    emails: list[str] = Field(..., alias="Email_Array")
    mobile_phones: list[MobilePhone] = []
    n_household_children: int | str = Field(..., alias="Children_HH", description="String number of children in the household")
    credit_range: str = Field(..., alias="Credit_Range")
    household_income: str = Field(..., alias="Income_HH", description="Descriptor of household income")
    household_net_worth: str = Field(..., alias="Net_Worth_HH", description="Descriptor of household net worth")
    home_owner_status: str = Field(..., alias="Home_Owner", description="Descriptor of home ownership status")
    marital_status: str = Field(..., alias="Marital_Status", description="Descriptor of marital status")
    occupation: str = Field(..., alias="Occupation_Detail")
    median_home_value: int | str = Field(..., alias="Median_Home_Value")
    education: str = Field(..., alias="Education")
    length_of_residence: int | str = Field(..., alias="Length_of_Residence")
    n_household_adults: int | str = Field(..., alias="Num_Adults_HH", description="String number of adults in the household")
    political_party: str = Field(..., alias="Political_Party")
    health_beauty_products: bool | str = Field(..., alias="Health_Beauty_Products")
    cosmetics: bool | str = Field(..., alias="Cosmetics")
    jewelry: bool | str = Field(..., alias="Jewelry")
    investment_type: Optional[bool] = Field(..., alias="Investment_Type")
    investments: bool | str = Field(..., alias="Investments")
    pet_owner: bool | str = Field(..., alias="Pet_Owner")
    pets_affinity: int | str = Field(..., alias="Pets_Affinity")
    health_affinity: int | str = Field(..., alias="Health_Affinity")
    diet_affinity: int | str = Field(..., alias="Diet_Affinity")
    fitness_affinity: int | str = Field(..., alias="Fitness_Affinity")
    outdoors_affinity: int | str = Field(..., alias="Outdoors_Affinity")
    boating_sailing_affinity: int | str = Field(..., alias="Boating_Sailing_Affinity")
    camping_hiking_climbing_affinity: int | str = Field(..., alias="Camping_Hiking_Climbing_Affinity")
    fishing_affinity: int | str = Field(..., alias="Fishing_Affinity")
    hunting_affinity: int | str = Field(..., alias="Hunting_Affinity")
    aerobics: int | str = Field(..., alias="Aerobics")
    nascar: int | str = Field(..., alias="NASCAR")
    scuba: int | str = Field(..., alias="Scuba")
    weight_lifting: int | str = Field(..., alias="Weight_Lifting")
    healthy_living_interest: int | str = Field(..., alias="Healthy_Living_Interest")
    motor_racing: int | str = Field(..., alias="Motor_Racing")
    foreign_travel: int | str = Field(..., alias="Travel_Foreign")
    self_improvement: int | str = Field(..., alias="Self_Improvement")
    walking: int | str = Field(..., alias="Walking")
    fitness: int | str = Field(..., alias="Fitness")
    ethnicity_detail: str = Field(..., alias="Ethnicity_Detail")
    ethnic_group: str = Field(..., alias="Ethnic_Group")

    @field_validator("investment_type", mode="before")
    def validate_investment_type(cls, v: str) -> Optional[bool]:
        """If empty string is passed to investment_type make it None."""
        if v == "":
            return None

        return v

    def hash(self: "PII") -> str:
        """Hash with instance attributes."""
        return f"{self.first_name} {self.last_name} {self.zip_code} {self.age} {self.household_net_worth} {self.household_income}"

    def __eq__(self, other: "PII") -> bool:
        """Approximate if two PII objects are equivalent based on attributes."""
        if not isinstance(other, PII):
            raise TypeError(f"Cannot compare PII with {type(other)}.")

        return self.hash() == other.hash()

    @classmethod
    def from_api_dict(cls, api_dict: dict[str, Any]) -> Self:
        """Read in the data and parse the mobile phones and gender."""
        mobile_phones: list[MobilePhone] = []
        for i in range(1, 3+1):
            if f"Mobile_Phone_{i}" in api_dict:
                phone: str = api_dict[f"Mobile_Phone_{i}"]

                if not phone:
                    continue

                dnc: bool = True if api_dict[f"Mobile_Phone_{i}_DNC"] == "1" else False
                mobile_phones.append(MobilePhone(phone=phone, do_not_call=dnc))

        if not api_dict["Email_Array"]:
            api_dict["Email_Array"] = []

        # Gender is returned as "M" or "F" in the 10026 API output
        if api_dict.get('Gender') == 'M':
            api_dict['Gender'] = 'Male'
        elif api_dict.get('Gender') == 'F':
            api_dict['Gender'] = 'Female'
        else:
            api_dict['Gender'] = 'Unknown'

        # Latitude and longitude are sometimes empty strings
        if api_dict["Latitude"] == "":
            api_dict["Latitude"] = None
        
        if api_dict["Longitude"] == "":
            api_dict["Longitude"] = None

        return cls(**api_dict, mobile_phones=mobile_phones)

    def as_lead_export(self) -> dict[str, Any]:
        """
        Dictionary output ready for insertion into a lead export.
        Emails and phone numbers are separated into unique attributes.
        """
        export_dict: dict[str, Any] = self.model_dump()

        # Remove unwanted fields
        if "id" in export_dict:
            del export_dict["id"]

        if "national_consumer_database" in export_dict:
            del export_dict["national_consumer_database"]

        # Separate Emails
        export_dict["email_1"] = None
        export_dict["email_2"] = None
        export_dict["email_3"] = None

        for pos, email in enumerate(self.emails[:3], start=1):
            export_dict[f"email_{pos}"] = email
    
        del export_dict["emails"]

        # Separate phone numbers
        export_dict["phone_1"] = None
        export_dict["phone_1_dnc"] = None
        export_dict["phone_2"] = None
        export_dict["phone_2_dnc"] = None
        export_dict["phone_3"] = None
        export_dict["phone_3_dnc"] = None

        phone: MobilePhone
        for pos, phone in enumerate(self.mobile_phones, start=1):
            export_dict[f"phone_{pos}"] = phone.phone
            export_dict[f"phone_{pos}_dnc"] = phone.do_not_call
        
        del export_dict["mobile_phones"]

        # Convert gender to string
        export_dict["gender"] = export_dict["gender"].value

        return export_dict

    @classmethod
    def create_fake(cls, seed: Optional[int] = None) -> Self:
        """Create a fake PII object with realistic-looking data."""
        if seed is not None:
            random.seed(seed)

        # Lists for generating realistic data
        first_names = ["James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda", "William", "Elizabeth"]
        last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"]
        streets = ["Main", "Oak", "Maple", "Cedar", "Pine", "Elm", "Washington", "Lake", "Hill", "Park"]
        cities = ["Springfield", "Franklin", "Clinton", "Madison", "Georgetown", "Salem", "Greenville", "Bristol", "Manchester", "Oxford"]
        states = ["CA", "TX", "FL", "NY", "IL", "PA", "OH", "GA", "NC", "MI"]
        occupations = ["Engineer", "Teacher", "Doctor", "Lawyer", "Accountant", "Manager", "Developer", "Designer", "Analyst", "Consultant"]
        education_levels = ["High School", "Some College", "Bachelors", "Masters", "Doctorate"]
        political_parties = ["Republican", "Democrat", "Independent", "None"]
        ethnicities = ["Caucasian", "African American", "Hispanic", "Asian", "Other"]
        marital_statuses = ["Single", "Married", "Divorced", "Widowed"]
        credit_ranges = ["Poor", "Fair", "Good", "Very Good", "Excellent"]
        income_ranges = ["0-25000", "25000-50000", "50000-75000", "75000-100000", "100000-150000", "150000+"]
        net_worth_ranges = ["0-100000", "100000-250000", "250000-500000", "500000-1000000", "1000000+"]

        # Generate a random date in the past 60 years
        today = datetime.now()
        birth_date = today - timedelta(days=random.randint(365*18, 365*80))  # Between 18 and 80 years old
        age = str((today - birth_date).days // 365)
        birth_month_year = birth_date.strftime("%m/%Y")

        # Generate random coordinates in continental US
        lat = random.uniform(24.396308, 49.384358)  # Approximate US boundaries
        lon = random.uniform(-125.000000, -66.934570)

        # Generate random email and phone
        email = f"{random.choice(string.ascii_lowercase)}{random.choice(string.ascii_lowercase)}{random.randint(100,999)}@example.com"
        phone = f"{random.randint(100,999)}{random.randint(100,999)}{random.randint(1000,9999)}"

        # Create fake PII data
        fake_data = {
            "Id": f"TEST_{random.randint(10000,99999)}",
            "First_Name": random.choice(first_names),
            "Last_Name": random.choice(last_names),
            "Address": f"{random.randint(100,9999)} {random.choice(streets)} St",
            "City": random.choice(cities),
            "State": random.choice(states),
            "Zip": f"{random.randint(10000,99999)}",
            "Zip4": f"{random.randint(1000,9999)}",
            "Fips_State_Code": f"{random.randint(1,56):02d}",
            "Fips_County_Code": f"{random.randint(1,999):03d}",
            "County_Name": f"{random.choice(['North', 'South', 'East', 'West'])} County",
            "Latitude": str(lat),
            "Longitude": str(lon),
            "Address_Type": random.choice(["H", "S", ""]),
            "Cbsa": str(random.randint(10000,99999)),
            "Census_Tract": str(random.randint(100000,999999)),
            "Census_Block_Group": str(random.randint(1,9)),
            "Census_Block": str(random.randint(1000,9999)),
            "Gender": random.choice([Gender.MALE, Gender.FEMALE]),
            "SCF": str(random.randint(100,999)),
            "DMA": str(random.randint(100,999)),
            "MSA": str(random.randint(100,999)),
            "Congressional_District": str(random.randint(1,435)),
            "HeadOfHousehold": random.choice(["Yes", "No"]),
            "Birth_Month_and_Year": birth_month_year,
            "Age": age,
            "Prop_Type": random.choice(["Single Family", "Multi Family", "Condo", "Apartment"]),
            "Email_Array": [email],
            "Children_HH": str(random.randint(0,5)),
            "Credit_Range": random.choice(credit_ranges),
            "Income_HH": random.choice(income_ranges),
            "Net_Worth_HH": random.choice(net_worth_ranges),
            "Home_Owner": random.choice(["Yes", "No"]),
            "Marital_Status": random.choice(marital_statuses),
            "Occupation_Detail": random.choice(occupations),
            "Median_Home_Value": str(random.randint(100000,1000000)),
            "Education": random.choice(education_levels),
            "Length_of_Residence": str(random.randint(1,30)),
            "Num_Adults_HH": str(random.randint(1,5)),
            "Political_Party": random.choice(political_parties),
            "Health_Beauty_Products": random.choice(["0", "1"]),
            "Cosmetics": random.choice(["0", "1"]),
            "Jewelry": random.choice(["0", "1"]),
            "Investment_Type": random.choice(["", "0", "1"]),
            "Investments": random.choice(["0", "1"]),
            "Pet_Owner": random.choice(["0", "1"]),
            "Pets_Affinity": str(random.randint(0,5)),
            "Health_Affinity": str(random.randint(0,5)),
            "Diet_Affinity": str(random.randint(0,5)),
            "Fitness_Affinity": str(random.randint(0,5)),
            "Outdoors_Affinity": str(random.randint(0,5)),
            "Boating_Sailing_Affinity": str(random.randint(0,5)),
            "Camping_Hiking_Climbing_Affinity": str(random.randint(0,5)),
            "Fishing_Affinity": str(random.randint(0,5)),
            "Hunting_Affinity": str(random.randint(0,5)),
            "Aerobics": str(random.randint(0,5)),
            "NASCAR": str(random.randint(0,5)),
            "Scuba": str(random.randint(0,5)),
            "Weight_Lifting": str(random.randint(0,5)),
            "Healthy_Living_Interest": str(random.randint(0,5)),
            "Motor_Racing": str(random.randint(0,5)),
            "Travel_Foreign": str(random.randint(0,5)),
            "Self_Improvement": str(random.randint(0,5)),
            "Walking": str(random.randint(0,5)),
            "Fitness": str(random.randint(0,5)),
            "Ethnicity_Detail": random.choice(ethnicities),
            "Ethnic_Group": random.choice(ethnicities),
        }

        # Create mobile phones
        mobile_phones = [
            MobilePhone(phone=phone, do_not_call=random.choice([True, False]))
        ]

        # Add 0-2 additional phone numbers
        for _ in range(random.randint(0, 2)):
            additional_phone = f"{random.randint(100,999)}{random.randint(100,999)}{random.randint(1000,9999)}"
            mobile_phones.append(MobilePhone(phone=additional_phone, do_not_call=random.choice([True, False])))

        return cls(**fake_data, mobile_phones=mobile_phones)  


class MD5WithPII(UniqueMD5):
    """
    A unique MD5 with several sentences but also including an attribute with
    a dictionary of PII data returned directly by the API.

    Note: In the future, instead of housing a top-level `pii` attribute, 
    encode each PII attribute with the appropriate data type for full model
    validation.
    """
    pii: PII

    def hash(self: "MD5WithPII") -> str:
        """Hash with PII instance attritutes."""
        return self.pii.hash()

    def __eq__(self, other: "MD5WithPII") -> bool:
        """Approximate if two MD5WithPII objects are equivalent based on PII."""
        if not isinstance(other, MD5WithPII):
            raise TypeError(f"Cannot compare MD5WithPII with {type(other)}.")

        return self.hash() == other.hash()
    
    def convert_dict_lead_export(self):
        """Convert to dictionary for lead export."""
        return {
            "md5": self.md5,
            "sentences": self.sentences,
            "pii": self.pii.as_lead_export()
        }