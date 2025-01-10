"""Format into CSV strings."""
import pandas as pd

from io import StringIO
from typing import Any

from real_intent.deliver.base import BaseOutputDeliverer
from real_intent.schemas import MD5WithPII


OUTPUT_COLUMNS: list[str] = [
    'first_name',
    'last_name',
    'email_1',
    'email_2',
    'email_3',
    'phone_1',
    'phone_1_dnc',
    'phone_2',
    'phone_2_dnc',
    'phone_3',
    'phone_3_dnc',
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
    'age',
    'gender',
    'address_type',
    'cbsa',
    'census_tract',
    'census_block_group',
    'census_block',
    'scf',
    'dma',
    'msa',
    'congressional_district',
    'head_of_household',
    'birth_month_and_year',
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
    'md5',
]


class CSVStringFormatter(BaseOutputDeliverer):
    """Format into CSV strings."""

    def __init__(
        self, 
        output_columns: list[str] | None = None, 
        renames: dict[str, str] | None = None
    ):
        self.output_columns = [] + (output_columns if output_columns is not None else OUTPUT_COLUMNS)
        self.renames = renames or {}

    @staticmethod
    def _unique_sentences(all_md5s: list[MD5WithPII]) -> set[str]:
        """Return unique sentences from all MD5s."""
        unique_sentences: set[str] = set()

        for md5 in all_md5s:
            unique_sentences.update(md5.sentences)

        return unique_sentences

    @staticmethod
    def _intent_columns(current_md5: MD5WithPII, unique_sentences: set[str]) -> dict[str, str]:
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

        # Execute renames if any
        pii_df.rename(columns=self.renames, inplace=True)

        return pii_df

    def _deliver(self, pii_md5s: list[MD5WithPII]) -> str:
        """
        Convert the unique MD5s into a CSV string.
        Returns empty string if no result.
        """
        pii_df: pd.DataFrame = self._as_dataframe(pii_md5s)

        if pii_df.empty:
            return ""

        # Convert to CSV string
        string_io = StringIO()
        pii_df.to_csv(string_io, index=False)
        return string_io.getvalue()
