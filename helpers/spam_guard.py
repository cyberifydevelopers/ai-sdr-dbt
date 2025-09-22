# helpers/spam_guard.py
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple
from tortoise.expressions import Q
from models.call_log import CallLog
from models.call_blocklist import CallBlocklist

E164 = re.compile(r"^\+\d{8,18}$")

# Tunables (or read from env)
MAX_CALLS_15M = 3           # >3 calls in 15m -> cooldown
COOLDOWN_MIN = 60           # minutes
SHORT_CALL_S = 10           # repeated sub-10s calls
SHORT_CALLS_6H = 5          # >5 short calls in 6h -> cooldown
TEMP_BLOCK_H = 24           # hours for repeated short calls

async def screen_number(number: Optional[str]) -> Tuple[str, Optional[str], Optional[datetime]]:
    """
    Returns (action, message, blocked_until)
      action: "allow" | "block" | "challenge"
    """
    now = datetime.utcnow()

    # 1) missing/invalid caller id -> optional challenge instead of outright block
    if not number or not E164.match(number):
        return "challenge", "Please say the two words 'blue lemon' to continue.", None

    # 2) manual blocklist
    bl = await CallBlocklist.get_or_none(phone_number=number)
    if bl and bl.blocked_until and bl.blocked_until > now:
        return "block", f"Sorry, your number is temporarily blocked. Reason: {bl.reason}", bl.blocked_until

    # 3) rate limit in last 15 minutes
    t15 = now - timedelta(minutes=15)
    recent = await CallLog.filter(
        Q(customer_number=number) & Q(call_started_at__gte=t15)
    ).count()
    if recent >= MAX_CALLS_15M:
        until = now + timedelta(minutes=COOLDOWN_MIN)
        await CallBlocklist.update_or_create(
            defaults={
                "reason": f"Rate limit: {recent} calls in 15m",
                "blocked_until": until,
                "hit_count": (bl.hit_count + 1) if bl else 1,
            },
            phone_number=number,
        )
        return "block", "Too many calls in a short time. Please try again later.", until

    # 4) repeated very short calls in last 6h
    t6h = now - timedelta(hours=6)
    short_calls = await CallLog.filter(
        Q(customer_number=number) & Q(call_started_at__gte=t6h) & Q(call_duration__lte=SHORT_CALL_S)
    ).count()
    if short_calls >= SHORT_CALLS_6H:
        until = now + timedelta(hours=TEMP_BLOCK_H)
        await CallBlocklist.update_or_create(
            defaults={
                "reason": f"{short_calls} short calls (<={SHORT_CALL_S}s) in 6h",
                "blocked_until": until,
                "hit_count": (bl.hit_count + 1) if bl else 1,
            },
            phone_number=number,
        )
        return "block", "Your number has been temporarily blocked due to repeated short calls.", until

    # 5) allow by default
    return "allow", None, None
