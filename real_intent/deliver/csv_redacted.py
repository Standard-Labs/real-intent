"""CSV ouput formatter with redacted PII."""
import pandas as pd

from io import StringIO
from typing import Any

from real_intent.deliver.csv import CSVStringFormatter, OUTPUT_COLUMNS
from real_intent.schemas import MD5WithPII
from real_intent.internal_logging import log

from faker import Faker

class CSVStringFormatterRedacted(CSVStringFormatter):
    """Format into CSV strings with redacted PII."""

    def __init__(self, output_columns: list[str] = OUTPUT_COLUMNS):
        super().__init__(output_columns)  
        self.fake = Faker()

    def _deliver(self, pii_md5s: list[MD5WithPII]) -> tuple[str, dict]:
        """
        Convert the unique MD5s into a CSV string with fake first and last names.
        Drop unnecessary PII columns.
        Returns:
            tuple[str, dict]: A tuple containing:
                - CSV string of the processed data with fake names.
                - Dictionary of fake-to-real name mappings for remapping later on.
                Returns ("", {}) if pii_df is empty.
        """
        log("info", "Starting delivery process with name replacement and PII removal.")

        pii_df: pd.DataFrame = self._as_dataframe(pii_md5s)

        if pii_df.empty:
            return "", {}
        
        # Remove unnecessary PII
        pii_df = pii_df.drop(columns=[
            'address',
            'zip_code',
            'email_1',
            'email_2',
            'email_3',
            'phone_1',
            'phone_2',
            'phone_3',
            'phone_1_dnc',
            'phone_2_dnc',
            'phone_3_dnc',
        ])

        name_mapping = {} 
        fake_names = set()

        for index, row in pii_df.iterrows():
            # ensuring unique to avoid issues when mapping back to original names
            while True:
                if row['gender'].lower() in ["m", "male"]:
                    fake_first = self.fake.first_name_male()
                else:
                    fake_first = self.fake.first_name_female()
                
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
