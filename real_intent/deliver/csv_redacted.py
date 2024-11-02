"""Format into CSV strings."""
import pandas as pd

from io import StringIO
from typing import Any

from real_intent.deliver.base import BaseOutputDeliverer
from real_intent.schemas import MD5WithPII
from real_intent.internal_logging import log

from faker import Faker

OUTPUT_COLUMNS: list[str] = [
    'md5',
    'first_name',
    'last_name',
    'address',
    'city',
    'state',
    'zip_code',
    'zip4',
    'fips_state_code',
    'fips_county_code',
    'county_name',
    'latitude',
    'longitude',
    'address_type',
    'cbsa',
    'census_tract',
    'census_block_group',
    'census_block',
    'gender',
    'scf',
    'dma',
    'msa',
    'congressional_district',
    'head_of_household',
    'birth_month_and_year',
    'age',
    'prop_type',
    'n_household_children',
    'credit_range',
    'household_income',
    'household_net_worth',
    'home_owner_status',
    'marital_status',
    'occupation',
    'median_home_value',
    'education',
    'length_of_residence',
    'n_household_adults',
    'political_party',
    'health_beauty_products',
    'cosmetics',
    'jewelry',
    'investment_type',
    'investments',
    'pet_owner',
    'pets_affinity',
    'health_affinity',
    'diet_affinity',
    'fitness_affinity',
    'outdoors_affinity',
    'boating_sailing_affinity',
    'camping_hiking_climbing_affinity',
    'fishing_affinity',
    'hunting_affinity',
    'aerobics',
    'nascar',
    'scuba',
    'weight_lifting',
    'healthy_living_interest',
    'motor_racing',
    'foreign_travel',
    'self_improvement',
    'walking',
    'fitness',
    'ethnicity_detail',
    'ethnic_group',
    'email_1',
    'email_2',
    'email_3',
    'phone_1',
    'phone_1_dnc',
    'phone_2',
    'phone_2_dnc',
    'phone_3',
    'phone_3_dnc',
]


class CSVStringFormatterRedacted(BaseOutputDeliverer):
    """Format into CSV strings."""

    def __init__(self, output_columns: list[str] = OUTPUT_COLUMNS):
        self.output_columns = [] + output_columns
        self.fake = Faker()

    @staticmethod
    def _unique_sentences(all_md5s: list[MD5WithPII]) -> set[str]:
        """Return unique sentences from all MD5s."""
        unique_sentences: set[str] = set()

        for md5 in all_md5s:
            unique_sentences.update(md5.sentences)

        return unique_sentences

    @staticmethod
    def _intent_columns(current_md5: MD5WithPII, unique_sentences: set[str]) -> dict[str, list]:
        """Keys: 1 column per intent category. Values: x if applies to the person."""
        intent_columns: dict[str, str] = {}

        for sentence in unique_sentences:
            intent_columns[sentence] = "x" if sentence in current_md5.sentences else ""

        return intent_columns

    def _as_dataframe(self, pii_md5s: list[MD5WithPII]) -> pd.DataFrame:
        """
        Convert the unique MD5s into a DataFrame ready to be converted to a CSV.
        """
        if not pii_md5s:
            return pd.DataFrame()
            
        # Calculate the unique sentences
        unique_sentences: set[str] = self._unique_sentences(pii_md5s)

        lead_dicts: list[dict[str, Any]] = [
            {
                "md5": md5.md5,
                **self._intent_columns(md5, unique_sentences),
                **md5.pii.as_lead_export()
            }
            for md5 in pii_md5s
        ]

        # Convert to DataFrame for exporting
        # MD5 should be first column, followed by sentences and then rest of data
        output_columns: list[str] = self.output_columns.copy()  # ensure instance is reusable
        output_columns[0:0] = (list_sentences := list(unique_sentences))
        pii_df: pd.DataFrame = pd.DataFrame(lead_dicts)[output_columns]
        

        # Rename intent columns for readability
        pii_df.rename(
            columns={sentence: sentence.split(">")[-1] for sentence in list_sentences}, 
            inplace=True
        )

        return pii_df

    def _deliver(self, pii_md5s: list[MD5WithPII]) -> tuple[str, dict]:
        """
        Convert the unique MD5s into a CSV string with fake first and last names.
            Returns:
                tuple[str, dict]: A tuple containing:
                    - CSV string of the processed data with fake names.
                    - Dictionary of fake-to-real name mappings.
                    Returns ("", {}) if pii_df is empty.
        """

        log("info", "Starting delivery process with name replacement and PII removal.")

        pii_df: pd.DataFrame = self._as_dataframe(pii_md5s)

        if pii_df.empty:
            return "", {}
        
        # Remove unnecessary PII
        pii_df = pii_df.drop(columns=[
            'address',
            'city',
            'state',
            'zip_code',
            'email_1',
            'email_2',
            'email_3',
            'phone_1',
            'phone_2',
            'phone_3',
        ])

        name_mapping = {} 
        fake_names = set()

        for index, row in pii_df.iterrows():

            # ensuring unique to avoid issues when mapping back to original names
            while True:
                fake_first = self.fake.first_name()
                fake_last = self.fake.last_name()

                if (fake_first, fake_last) not in fake_names:  
                    break 

            fake_names.add((fake_first, fake_last))

            name_mapping[fake_first, fake_last] = row['first_name'], row['last_name']
            pii_df.at[index, 'first_name'] = fake_first
            pii_df.at[index, 'last_name'] = fake_last

            log("info", f"Replaced real first,last name '{row['first_name']} {row['last_name']}' "
                     f"with fake name '{fake_first} {fake_last}'.")


        # Convert to CSV string
        string_io = StringIO()
        pii_df.to_csv(string_io, index=False)
        return string_io.getvalue(), name_mapping
