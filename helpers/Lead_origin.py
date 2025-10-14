# helpers/origin.py  (new file)
from typing import Optional
from models.lead import Lead

def set_origin_defaults(lead: Lead, origin: str, origin_meta: Optional[str] = None) -> None:
    lead.origin = origin
    lead.origin_meta = origin_meta
