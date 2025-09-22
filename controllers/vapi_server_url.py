# controllers/vapi_server_url.py
from fastapi import APIRouter, Request, Response
from helpers.spam_guard import screen_number
from helpers.vapi_helper import get_headers  # already in your repo
router = APIRouter()

@router.post("/webhooks/vapi")
async def vapi_server_url(req: Request):
    body = await req.json()
    msg = (body or {}).get("message", {})
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
    # Option A: inline config; Option B: return a saved assistantId
    return {"assistantId": "<YOUR_DEFAULT_ASSISTANT_ID>"}
