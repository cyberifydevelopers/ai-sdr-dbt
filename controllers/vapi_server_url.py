# controllers/vapi_server_url.py
from fastapi import APIRouter, Request, Response
from json import JSONDecodeError
import json
import logging

from helpers.spam_guard import screen_number
from helpers.vapi_helper import get_headers  # already in your repo

router = APIRouter()
log = logging.getLogger("vapi_webhook")

async def parse_incoming_body(req: Request) -> dict:
    """
    Safely parse JSON/form bodies. Returns {} on empty/invalid payloads.
    Never throws JSONDecodeError.
    """
    ctype = (req.headers.get("content-type") or "").lower()

    # Try JSON first if announced
    if "application/json" in ctype:
        try:
            return await req.json()
        except (JSONDecodeError, ValueError) as e:
            log.warning("Invalid JSON body: %s", e)

    # Try form payloads (some providers send x-www-form-urlencoded)
    if "application/x-www-form-urlencoded" in ctype or "multipart/form-data" in ctype:
        try:
            form = await req.form()
            # If the provider wraps json in a field like `payload`, decode it
            if "payload" in form:
                try:
                    return json.loads(form["payload"])
                except (JSONDecodeError, TypeError) as e:
                    log.warning("Invalid JSON in form payload: %s", e)
                    return dict(form)
            return dict(form)
        except Exception as e:
            log.warning("Form parse failed: %s", e)

    # Fallback: raw body (sometimes no/incorrect content-type is sent)
    try:
        raw = await req.body()
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))
    except (JSONDecodeError, UnicodeDecodeError) as e:
        log.warning("Raw body not JSON: %s", e)
        return {}
    except Exception as e:
        log.exception("Unexpected error reading body: %s", e)
        return {}

@router.post("/webhooks/vapi")
async def vapi_server_url(req: Request):
    body = await parse_incoming_body(req)

    # If body is empty or not the expected shape, gracefully ignore
    msg = (body or {}).get("message", {})
    if not msg:
        # Many providers send health checks / empty retries
        return Response(status_code=204)

    if msg.get("type") != "assistant-request":
        return Response(status_code=204)

    call = msg.get("call", {}) or {}
    incoming_number = (call.get("from") or {}).get("phoneNumber")

    action, msg_text, _until = await screen_number(incoming_number)

    if action == "block":
        # hard reject (spoken once then hangup)
        return {"error": msg_text or "Your number is blocked."}

    if action == "challenge":
        # lightweight challenge assistant (DTMF/phrase). If passed, your main assistant can take over.
        return {
            "assistant": {
                "name": "Humanity Spam Shield",
                "firstMessage": "Quick check: please say the two words 'blue lemon' to continue.",
                "model": {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": (
                            "You are a gatekeeper. If the user says the exact phrase 'blue lemon' "
                            "within 10 seconds, say 'Thanks, connecting you now.' and end the call with status 'pass'. "
                            "Otherwise say 'Verification failed' and end the call."
                        )}
                    ]
                },
                "voice": {"provider": "11labs", "voiceId": "shimmer"},
                "endCallPhrases": ["pass", "failed"]
            }
        }

    # action == "allow": proceed with your normal assistant
    return {"assistantId": "<YOUR_DEFAULT_ASSISTANT_ID>"}
