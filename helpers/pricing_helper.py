from typing import Optional, Tuple
from models.billing import PricingSettings

DEFAULT_CURRENCY = "USD"

async def get_active_pricing() -> Tuple[str, int, int]:
    """
    Returns (currency, call_millicents_per_second, text_cents_per_message)
    """
    row: Optional[PricingSettings] = await PricingSettings.all().order_by("-id").first()
    if not row:
        return (DEFAULT_CURRENCY, 0, 0)
    return (
        row.currency or DEFAULT_CURRENCY,
        row.call_millicents_per_second or 0,
        row.text_cents_per_message or 0,
    )