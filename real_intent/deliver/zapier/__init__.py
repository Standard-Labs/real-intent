"""Deliver to Zapier webhooks."""
import requests
from typing import Any
from functools import partial
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from real_intent.internal_logging import log
from real_intent.deliver.base import BaseOutputDeliverer
from real_intent.schemas import MD5WithPII

class ZapierDeliverer(BaseOutputDeliverer):

    def __init__(self, webhook_urls: list[str], per_lead_insights: dict[str, str] = {}):
        """Initialize the deliverer"""
        self.webhook_urls: list[str] = webhook_urls
        self.per_lead_insights: dict[str, str] = per_lead_insights


    def _warn_dnc(self, pii_md5s: list[MD5WithPII]) -> None:
        """Log a warning if any of the leads are on the DNC list."""
        for md5_with_pii in pii_md5s:
            if any(phone.do_not_call for phone in md5_with_pii.pii.mobile_phones):
                log(
                    "warn",
                    (
                        f"At least 1 lead in the Zapier deliverer was on "
                        f"the DNC list. Please validate the lead before delivery."
                    )
                )
                break


    def _deliver(self, pii_md5s: list[MD5WithPII]) -> bool:
        """Deliver the formatted data to Zapier webhooks."""

        self._warn_dnc(pii_md5s)
        payload = self._format(pii_md5s)

        # payload will be constant, so we can use partial to make it as a prefilled argument
        with ThreadPoolExecutor(max_workers=5) as executor:
            deliver_one = partial(self._deliver_one_url, payload)
            results = list(executor.map(deliver_one, self.webhook_urls))
        return all(results)


    def _deliver_one_url(self, payload: list[dict[str, Any]], webhook_url: str) -> bool:
        """Deliver batch of leads to a singular Zapier webhook."""
        
        response = requests.post(webhook_url, json=payload)

        if response.status_code != 200:
            log(
                "error",
                (
                    f"Failed to deliver to Zapier webhook {webhook_url}. "
                    f"Status code: {response.status_code}, "
                    f"Response: {response.text}"
                )
            )
            return False
            
        return True
    
    
    def _format(self, pii_md5s: list[MD5WithPII]) -> list[dict[str, Any]]:
        """
        Format the leads into a deliverable format.

        Seperates phone numbers and emails (convert_dict_lead_export()), adds insights to the dict, and combines 
        sentences into a single string.
        
        Returns the formatted list of these dictionary objects:
        [
            {
                "md5": "...",
                "pii": {...},
                "insight": "...",
                "sentences": "... | ... | ... | ...",
                "date_delivered": "...."
            },
            {
                "md5": "...",
                "pii": {...},
                "insight": "",
                "sentences": "... | ... | ...",
                "date_delivered": "...."
                ...
            },
        ]
        """

        formatted_leads = []
        for pii_md5 in pii_md5s:

            md5_dict = pii_md5.convert_dict_lead_export()

            # convert all values to string, needed for Zapier consistency
            md5_dict["pii"] = {key: (str(value) if value is not None else None) for key, value in md5_dict["pii"].items()}

            md5_dict["insight"] = self.per_lead_insights.get(md5_dict["md5"], "")

            md5_dict["sentences"] = " | ".join(md5_dict["sentences"])

            md5_dict["date_delivered"] = datetime.now().strftime("%Y-%m-%d")

            formatted_leads.append(md5_dict)

        return formatted_leads

