import re
from zoneinfo import ZoneInfo
import phonenumbers

_TZ_ALIASES = {
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "pacific time": "America/Los_Angeles",
    "america los angeles": "America/Los_Angeles",
    "los angeles": "America/Los_Angeles",
    "est": "America/New_York",
    "edt": "America/New_York",
    "eastern time": "America/New_York",
    # add more if needed
}

def normalize_phone(raw: str, default_region: str = "US") -> str:
    s = (raw or "").strip().lower()
    # convert 'plus' to '+' and remove spaces/hyphens/parentheses
    s = re.sub(r"\bplus\b", "+", s)
    s = re.sub(r"[^\d+]", "", s)
    # if missing leading '+', try to parse with region and reformat
    try:
        if not s.startswith("+"):
            num = phonenumbers.parse(s, default_region)
        else:
            num = phonenumbers.parse(s, None)
        if phonenumbers.is_valid_number(num):
            return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        pass
    # last resort: ensure '+' + digits
    if s and not s.startswith("+"):
        s = "+" + s
    return s

def normalize_timezone(raw: str) -> str:
    s = (raw or "").strip().lower()
    s = s.replace("-", " ").replace("_", " ").strip()
    if s in _TZ_ALIASES:
        return _TZ_ALIASES[s]
    # try "America Los Angeles" -> "America/Los_Angeles"
    if " " in s and "/" not in s:
        parts = [p.capitalize() for p in s.split()]
        guess = "/".join([" ".join(parts[:-1]), parts[-1]]).replace(" ", "_")
        try:
            ZoneInfo(guess)
            return guess
        except Exception:
            pass
    # try as-is with underscores
    candidate = s.replace(" ", "_")
    try:
        ZoneInfo(candidate)
        return candidate
    except Exception:
        return "UTC"

def normalize_time_hhmm(raw: str) -> str:
    # Accept "10 a.m.", "10am", "10:00 am", "10:00" etc. → "10:00"
    s = (raw or "").lower().strip().replace(".", "")
    m = re.match(r"^(\d{1,2})(?::?(\d{2}))?\s*(am|pm)?$", s)
    if not m:
        return raw
    hh = int(m.group(1))
    mm = int(m.group(2) or "0")
    ampm = m.group(3)
    if ampm == "pm" and hh != 12: hh += 12
    if ampm == "am" and hh == 12: hh = 0
    return f"{hh:02d}:{mm:02d}"

def normalize_date_iso(raw: str) -> str:
    # Accept "26th of October 2025" → "2025-10-26" if model ever returns natural text
    from dateutil import parser
    try:
        dt = parser.parse(raw, dayfirst=False, fuzzy=True)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return raw

def normalize_extracted(ap):
    """
    ap = AppointmentExtracted pydantic model (or dict-like).
    Mutates/returns a dict with normalized fields.
    """
    d = ap.model_dump() if hasattr(ap, "model_dump") else dict(ap)
    d["phone"] = normalize_phone(d.get("phone", ""))
    d["timezone"] = normalize_timezone(d.get("timezone") or "UTC")
    d["time"] = normalize_time_hhmm(d.get("time", ""))
    d["date"] = normalize_date_iso(d.get("date", ""))
    # Trim notes/location to None if empty strings
    d["notes"] = (d.get("notes") or None)
    d["location"] = (d.get("location") or None)
    return d
