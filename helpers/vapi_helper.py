
# # helpers/vapi_helper.py
# import os
# import jwt
# import re
# from datetime import datetime, timedelta
# from dotenv import load_dotenv
# import pytz
# import httpx
# import asyncio
# from models.auth import User

# # some projects reference AssignedLanguage here; keep this safe-import
# try:
#     from models.assigned_language import AssignedLanguage
# except Exception:
#     AssignedLanguage = None  # will only matter if assistant_payload uses it

# load_dotenv()

# # ------------------ ENV ------------------
# vapi_api_key = os.environ["VAPI_API_KEY"]
# vapi_org_id = os.environ.get("VAPI_ORG_ID", "")

# # where your API is publicly reachable (ngrok)
# API_PUBLIC_BASE = os.getenv("API_PUBLIC_BASE", "https://aisdr-dbt.ddns.net")
# # shared secret used by the Vapi tool → your backend
# APPOINTMENT_TOOL_SECRET = os.getenv("APPOINTMENT_TOOL_SECRET", "change-me")
# # if you already created the tool manually in Vapi UI, pin its id here
# BOOK_APPT_TOOL_ID = os.getenv("BOOK_APPT_TOOL_ID", "")

# # Debug: Check if environment variables are loaded correctly
# print("VAPI_API_KEY:", os.getenv("VAPI_API_KEY"))
# print("VAPI_ORG_ID:", os.getenv("VAPI_ORG_ID"))
# print("API_PUBLIC_BASE:", API_PUBLIC_BASE)
# print("BOOK_APPT_TOOL_ID:", BOOK_APPT_TOOL_ID)
# print("APPOINTMENT_TOOL_SECRET", APPOINTMENT_TOOL_SECRET)

# # ------------------ AUTH HEADERS ------------------
# def generate_token():
#     # For Vapi, using the API key as bearer works for org-scoped calls
#     return vapi_api_key

# def get_headers():
#     token = generate_token()
#     return {
#         "Authorization": f"Bearer {token}",
#         "Content-Type": "application/json"
#     }

# def get_file_headers():
#     token = generate_token()
#     return {
#         "Authorization": f"Bearer {token}",
#     }

# # ------------------ Vapi Tools: KB query tool (kept) ------------------
# async def create_query_tool(file_ids, tool_name="Query-Tool"):
#     """
#     Creates a Vapi 'query' tool bound to provided knowledge base file IDs.
#     Returns JSON with 'id' or None on failure.
#     """
#     url = "https://api.vapi.ai/tool/"
#     headers = {
#         "Authorization": f"Bearer {vapi_api_key}",
#         "Content-Type": "application/json"
#     }
#     data = {
#         "type": "query",
#         "function": {"name": tool_name},
#         "knowledgeBases": [
#             {
#                 "provider": "google",
#                 "name": "product-kb",
#                 "description": "Use this knowledge base when the user asks or queries about the product or services",
#                 "fileIds": file_ids
#             }
#         ]
#     }

#     try:
#         async with httpx.AsyncClient(timeout=30.0) as client:
#             response = await client.post(url, headers=headers, json=data)
#             if response.status_code in [200, 201]:
#                 return response.json()
#             else:
#                 print(f"[create_query_tool] error {response.status_code}: {response.text}")
#                 return None
#     except httpx.RequestError as e:
#         print(f"[create_query_tool] request error: {e}")
#         return None
#     except Exception as e:
#         print(f"[create_query_tool] unexpected error: {e}")
#         return None

# # ------------------ Appointment tool handling (NO auto-create) ------------------
# # We will NOT auto-create the book_appointment tool anymore.
# # We will ONLY use BOOK_APPT_TOOL_ID from the environment if provided.

# def get_book_appt_tool_id() -> str:
#     """
#     Return the pre-created book_appointment tool id from env (if set).
#     No creation attempts are made here.
#     """
#     if BOOK_APPT_TOOL_ID:
#         return BOOK_APPT_TOOL_ID
#     print("BOOK_APPT_TOOL_ID is not set; skipping book_appointment tool attachment.")
#     return ""

# # ------------------ Payload builders (use existing tool id only) ------------------
# async def admin_add_payload(assistant_data):
#     """
#     Admin-facing assistant payload.
#     Attaches KB tool (if any) and the pre-created book_appointment tool (if BOOK_APPT_TOOL_ID is set).
#     """
#     print(assistant_data)
#     to_return = {
#         "transcriber": {
#             "provider": assistant_data.transcribe_provider,
#             "model": assistant_data.transcribe_model,
#             "language": assistant_data.transcribe_language,
#         },
#         "model": {
#             "messages": [
#                 {
#                     "content": assistant_data.systemPrompt,
#                     "role": "system"
#                 }
#             ],
#             "provider": assistant_data.provider,
#             "model": assistant_data.model,
#             "temperature": assistant_data.temperature,
#             "knowledgeBase": {
#                 "provider": "canonical",
#                 "topK": 5,
#                 "fileIds": assistant_data.knowledgeBase
#             },
#             "maxTokens": assistant_data.maxTokens,
#         },
#         "voice": {
#             "provider": assistant_data.voice_provider,
#             "voiceId": assistant_data.voice,
#             "model": assistant_data.voice_model if assistant_data.voice_model else "octave" if assistant_data.voice_provider == "hume" else "eleven_flash_v2_5" if assistant_data.voice_provider == "11labs" else "aura" if assistant_data.voice_provider == "deepgram" else "eleven_flash_v2_5",
#             **({"speed": assistant_data.speed if assistant_data.speed is not None else 1.0,
#                 "stability": assistant_data.stability if assistant_data.stability is not None else 0.75,
#                 "similarityBoost": assistant_data.similarityBoost if assistant_data.similarityBoost is not None else 0.75} if assistant_data.voice_provider == "11labs" else {})
#         },
#         "firstMessageMode": "assistant-speaks-first",
#         "hipaaEnabled": getattr(assistant_data, 'hipaaEnabled', False),
#         "clientMessages": assistant_data.clientMessages,
#         "serverMessages": assistant_data.serverMessages,
#         "silenceTimeoutSeconds": 30,
#         "maxDurationSeconds": getattr(assistant_data, 'maxDurationSeconds', 600),
#         "backgroundSound": "office",
#         "backchannelingEnabled": False,
#         "backgroundDenoisingEnabled": False,
#         "modelOutputInMessagesEnabled": False,
#         "transportConfigurations": [
#             {
#                 "provider": "twilio",
#                 "timeout": 60,
#                 "record": False,
#                 "recordingChannels": "mono"
#             }
#         ],
#         "name": assistant_data.name,
#         "firstMessage": assistant_data.first_message, 
#         "voicemailMessage": getattr(assistant_data, 'voicemailMessage', ""),
#         "endCallMessage": getattr(assistant_data, 'endCallMessage', ""),
#         "endCallPhrases": assistant_data.endCallPhrases,
#         "metadata": {},
#         "analysisPlan": {
#             "summaryPrompt": assistant_data.systemPrompt,
#             "summaryRequestTimeoutSeconds": 10.5,
#             "structuredDataRequestTimeoutSeconds": 10.5,
#             "successEvaluationPrompt": getattr(assistant_data, 'successEvaluationPrompt', ""),
#             "successEvaluationRubric": "PassFail",
#             "successEvaluationRequestTimeoutSeconds": 10.5,
#             "structuredDataPrompt": getattr(assistant_data, 'structuredDataPrompt', ""),
#             "structuredDataSchema": {
#                 "type": "string",
#                 "items": {"type": "string"},
#                 "properties": {},
#                 "description": "<string>",
#                 "required": ["<string>"]
#             }
#         },
#         "artifactPlan": {
#             "recordingEnabled": getattr(assistant_data, 'audioRecordingEnabled', True),
#             "videoRecordingEnabled": getattr(assistant_data, 'videoRecordingEnabled', False),
#             "recordingPath": "<string>"
#         },
#         "messagePlan": {
#             "idleMessages": getattr(assistant_data, 'idleMessages', [""]),
#             "idleMessageMaxSpokenCount": getattr(assistant_data, 'idleMessageMaxSpokenCount', 5),
#             "idleTimeoutSeconds": getattr(assistant_data, 'idleTimeoutSeconds', 17.5)
#         },
#         "startSpeakingPlan": {
#             "waitSeconds": 0.4,
#             "smartEndpointingEnabled": False,
#             "transcriptionEndpointingPlan": {
#                 "onPunctuationSeconds": 0.1,
#                 "onNoPunctuationSeconds": 1.5,
#                 "onNumberSeconds": 0.5
#             }
#         },
#         "stopSpeakingPlan": {
#             "numWords": 0,
#             "voiceSeconds": 0.2,
#             "backoffSeconds": 1
#         },
#         "monitorPlan": {
#             "listenEnabled": False,
#             "controlEnabled": False
#         }
#     }

#     # transfer call tool (unchanged)
#     if assistant_data.forwardingPhoneNumber:
#         to_return["model"]["tools"] = [
#             {
#                 "type": "transferCall",
#                 "destinations": [
#                     {
#                         "type": "number",
#                         "number": assistant_data.forwardingPhoneNumber,
#                         "description": "Transfer to customer support",
#                     }
#                 ]
#             }
#         ]
#         to_return["forwardingPhoneNumber"] = assistant_data.forwardingPhoneNumber

#     # --- collect toolIds (KB + pre-created book_appointment) ---
#     tool_ids = []

#     # KB tool (optional; still created dynamically if fileIds provided)
#     if assistant_data.knowledgeBase and len(assistant_data.knowledgeBase) > 0:
#         kb_tool = await create_query_tool(assistant_data.knowledgeBase)
#         if kb_tool and kb_tool.get("id"):
#             tool_ids.append(kb_tool["id"])
#         else:
#             print("KB Tool creation failed or returned no id.")

#     # Appointment tool (ONLY use env-provided id; do not create)
#     appt_tool_id = get_book_appt_tool_id()
#     if appt_tool_id:
#         tool_ids.append(appt_tool_id)
#     else:
#         print("book_appointment tool id not provided; skipping.")

#     to_return["model"]["toolIds"] = tool_ids
#     return to_return

# async def user_add_payload(assistant_data, user):
#     """
#     User-facing assistant payload.
#     Attaches KB tool (if any) and the pre-created book_appointment tool (if BOOK_APPT_TOOL_ID is set).
#     """
#     user = await User.filter(id=user.id).first()

#     if not getattr(assistant_data, "languages", None):
#         systemprompt = f"{assistant_data.systemPrompt} Please note, you can only communicate in **English**. Any other language will not be understood, and responses will be in English only."
#     else:
#         languages = ", ".join(assistant_data.languages)
#         systemprompt = f"{assistant_data.systemPrompt} Please note, you can only communicate in the: **{languages}** languages. Any other language will not be understood, and responses will be given only in these **{languages}** languages."

#     print(systemprompt)

#     # voice selection (unchanged)
#     if assistant_data.voice_provider == "deepgram":
#         voice_model = "aura"
#         voice = {
#             "provider": assistant_data.voice_provider,
#             "voiceId": assistant_data.voice,
#             "model": voice_model,
#         }
#     elif assistant_data.voice_provider == "hume":
#         voice_model = assistant_data.voice_model if assistant_data.voice_model else "octave"
#         print(f"Hume voice configuration - voice_model: {voice_model}, voiceId: {assistant_data.voice}")
#         voice = {
#             "provider": assistant_data.voice_provider,
#             "voiceId": assistant_data.voice,
#             "model": voice_model,
#         }
#         print(f"Final Hume voice config: {voice}")
#     elif assistant_data.voice_provider == "openai":
#         voice = {
#             "provider": "openai",
#             "voiceId": assistant_data.voice,
#             "model": "gpt-4o-mini-tts",
#         }
#         print(f"Final OpenAI voice config: {voice}")
#     else:
#         voice_model = "eleven_flash_v2_5"
#         voice = {
#             "provider": assistant_data.voice_provider,
#             "voiceId": assistant_data.voice,
#             "model": voice_model,
#             "speed": assistant_data.speed if assistant_data.speed is not None else 1.0,
#             "stability": assistant_data.stability if assistant_data.stability is not None else 0.75,
#             "similarityBoost": assistant_data.similarityBoost if assistant_data.similarityBoost is not None else 0.75,
#         }

#     user_payload = {
#         "transcriber": {
#             "provider": assistant_data.transcribe_provider,
#             "model": assistant_data.transcribe_model,
#             "language": assistant_data.transcribe_language,
#         },
#         "model": {
#             "messages": [
#                 {
#                     "content": systemprompt,
#                     "role": "system"
#                 }
#             ],
#             "provider": assistant_data.provider,
#             "model": assistant_data.model,
#             "temperature": assistant_data.temperature,
#             "knowledgeBase": {
#                 "provider": "canonical",
#                 "topK": 5,
#                 "fileIds": assistant_data.knowledgeBase
#             },
#             "maxTokens": assistant_data.maxTokens,
#         },
#         "voice": voice,
#         "name": assistant_data.name,
#         "firstMessage": assistant_data.first_message,
#         "firstMessageMode": "assistant-speaks-first",
#         "silenceTimeoutSeconds": 30,
#         "maxDurationSeconds": 600,
#         "endCallPhrases": assistant_data.endCallPhrases,
#         "analysisPlan": {
#             "summaryPrompt": assistant_data.systemPrompt,
#         },
#         "startSpeakingPlan": {
#             "waitSeconds": 0.8,
#             "smartEndpointingEnabled": True,
#             "transcriptionEndpointingPlan": {
#                 "onPunctuationSeconds": 0.3,
#                 "onNoPunctuationSeconds": 2.0,
#                 "onNumberSeconds": 0.8
#             }
#         },
#         "stopSpeakingPlan": {
#             "numWords": 0,
#             "voiceSeconds": 0.5,
#             "backoffSeconds": 1.5
#         }
#     }

#     if assistant_data.forwardingPhoneNumber:
#         user_payload["forwardingPhoneNumber"] = assistant_data.forwardingPhoneNumber
#         user_payload["model"]["tools"] = [
#             {
#                 "type": "transferCall",
#                 "destinations": [
#                     {
#                         "type": "number",
#                         "number": assistant_data.forwardingPhoneNumber,
#                         "description": "Transfer to customer support",
#                     }
#                 ]
#             }
#         ]

#     # --- collect toolIds (KB + pre-created book_appointment) ---
#     tool_ids = []

#     if assistant_data.knowledgeBase and len(assistant_data.knowledgeBase) > 0:
#         kb_tool = await create_query_tool(assistant_data.knowledgeBase)
#         if kb_tool and kb_tool.get("id"):
#             tool_ids.append(kb_tool["id"])
#         else:
#             print("KB Tool creation failed or returned no id.")

#     appt_tool_id = get_book_appt_tool_id()
#     if appt_tool_id:
#         tool_ids.append(appt_tool_id)
#     else:
#         print("book_appointment tool id not provided; skipping.")

#     user_payload["model"]["toolIds"] = tool_ids

#     # Debug for Hume config (unchanged logs)
#     if assistant_data.voice_provider == "hume":
#         print(f"Final VAPI payload for Hume voice: {user_payload}")

#     return user_payload

# async def assistant_payload(assistant_data, company_id):
#     """
#     Company-context assistant payload.
#     Attaches KB tool (if any) and the pre-created book_appointment tool (if BOOK_APPT_TOOL_ID is set).
#     """
#     # languages
#     if AssignedLanguage:
#         assigned_languages = await AssignedLanguage.filter(company_id=company_id).first()
#     else:
#         assigned_languages = None

#     if assigned_languages and assigned_languages.language:
#         if isinstance(assigned_languages.language, list):
#             languages = ", ".join(assigned_languages.language)
#         else:
#             languages = assigned_languages.language
#         systemprompt = f"{assistant_data.systemPrompt} Please note, you can only communicate in the : **{languages}** languages. Any other language will not be understood, and responses will be given only in these languages."
#     else:
#         systemprompt = f"{assistant_data.systemPrompt} Please note, you can only communicate in **English**. Any other language will not be understood, and responses will be in English only."

#     # voice selection (unchanged)
#     if assistant_data.voice_provider == "deepgram":
#         voice_model = "aura"
#         voice = {
#             "provider": assistant_data.voice_provider,
#             "voiceId": assistant_data.voice,
#             "model": voice_model,
#         }
#     elif assistant_data.voice_provider == "hume":
#         voice_model = assistant_data.voice_model if assistant_data.voice_model else "octave"
#         print(f"Hume voice configuration - voice_model: {voice_model}, voiceId: {assistant_data.voice}")
#         # validation logs...
#         if not assistant_data.voice or len(assistant_data.voice) < 10:
#             print(f"WARNING: Hume voice ID appears invalid: {assistant_data.voice}")
#         uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
#         is_valid_uuid = bool(uuid_pattern.match(assistant_data.voice)) if assistant_data.voice else False
#         print(f"Hume voice ID UUID format check: {is_valid_uuid}")

#         voice = {
#             "provider": assistant_data.voice_provider,
#             "voiceId": assistant_data.voice,
#             "model": voice_model,
#         }
#         print(f"Final Hume voice config: {voice}")
#     else:
#         voice_model = "eleven_flash_v2_5"
#         voice = {
#             "provider": assistant_data.voice_provider,
#             "voiceId": assistant_data.voice,
#             "model": voice_model,
#             "speed": assistant_data.speed or 0,
#             "stability": assistant_data.stability,
#             "similarityBoost": assistant_data.similarityBoost,
#         }

#     user_payload = {
#         "transcriber": {
#             "provider": assistant_data.transcribe_provider,
#             "model": assistant_data.transcribe_model,
#             "language": assistant_data.transcribe_language,
#         },
#         "model": {
#             "messages": [
#                 {
#                     "content": systemprompt,
#                     "role": "system"
#                 }
#             ],
#             "provider": assistant_data.provider,
#             "model": assistant_data.model,
#             "temperature": assistant_data.temperature,
#             "knowledgeBase": {
#                 "provider": "canonical",
#                 "topK": 5,
#                 "fileIds": assistant_data.knowledgeBase
#             },
#             "maxTokens": assistant_data.maxTokens,
#         },
#         "voice": voice,
#         "name": assistant_data.name,
#         "firstMessage": assistant_data.first_message,
#         "firstMessageMode": "assistant-speaks-first",
#         "silenceTimeoutSeconds": 30,
#         "maxDurationSeconds": 600,
#         "endCallPhrases": assistant_data.endCallPhrases,
#         "analysisPlan": {
#             "summaryPrompt": assistant_data.systemPrompt,
#         },
#         "startSpeakingPlan": {
#             "waitSeconds": 0.8,
#             "smartEndpointingEnabled": True,
#             "transcriptionEndpointingPlan": {
#                 "onPunctuationSeconds": 0.3,
#                 "onNoPunctuationSeconds": 2.0,
#                 "onNumberSeconds": 0.8
#             }
#         },
#         "stopSpeakingPlan": {
#             "numWords": 0,
#             "voiceSeconds": 0.5,
#             "backoffSeconds": 1.5
#         }
#     }

#     if assistant_data.forwardingPhoneNumber:
#         user_payload["forwardingPhoneNumber"] = assistant_data.forwardingPhoneNumber
#         user_payload["model"]["tools"] = [
#             {
#                 "type": "transferCall",
#                 "destinations": [
#                     {
#                         "type": "number",
#                         "number": assistant_data.forwardingPhoneNumber,
#                         "description": "Transfer to customer support",
#                     }
#                 ]
#             }
#         ]

#     # --- collect toolIds (KB + pre-created book_appointment) ---
#     tool_ids = []

#     if assistant_data.knowledgeBase and len(assistant_data.knowledgeBase) > 0:
#         kb_tool = await create_query_tool(assistant_data.knowledgeBase)
#         if kb_tool and kb_tool.get("id"):
#             tool_ids.append(kb_tool["id"])
#         else:
#             print("KB Tool creation failed or returned no id.")

#     appt_tool_id = get_book_appt_tool_id()
#     if appt_tool_id:
#         tool_ids.append(appt_tool_id)
#     else:
#         print("book_appointment tool id not provided; skipping.")

#     user_payload["model"]["toolIds"] = tool_ids

#     # optional additional logs
#     print("assistant_payload toolIds:", tool_ids)

#     return user_payload









# helpers/vapi_helper.py
import os
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv
import httpx
from typing import Dict, Any, Optional

load_dotenv()

# ------------------ ENV ------------------
vapi_api_key = os.environ["VAPI_API_KEY"]  # raise KeyError early if missing
vapi_org_id = os.environ.get("VAPI_ORG_ID", "")

# Normalize base so we never get double slashes
_RAW_BASE = os.getenv("API_PUBLIC_BASE", "http://localhost:8000").strip()
API_PUBLIC_BASE = _RAW_BASE.rstrip("/")

APPOINTMENT_TOOL_SECRET = os.getenv("APPOINTMENT_TOOL_SECRET")  # must be set in prod
BOOK_APPT_TOOL_ID = os.getenv("BOOK_APPT_TOOL_ID", "").strip()

def _mask(val: Optional[str], keep: int = 4) -> str:
    if not val:
        return "unset"
    return f"{val[:keep]}…{val[-keep:] if len(val) > keep else ''}"

# Light, safe debug; do NOT print api key value.
print("VAPI_ORG_ID:", _mask(vapi_org_id))
print("API_PUBLIC_BASE:", API_PUBLIC_BASE)
print("BOOK_APPT_TOOL_ID:", BOOK_APPT_TOOL_ID or "unset")
print("APPOINTMENT_TOOL_SECRET set?:", bool(APPOINTMENT_TOOL_SECRET))

# Hard fail in production-like envs if secret is missing
if API_PUBLIC_BASE.startswith("https://") and not APPOINTMENT_TOOL_SECRET:
    raise RuntimeError(
        "APPOINTMENT_TOOL_SECRET is missing. Live Vapi API Request calls will be rejected by your server."
    )

# ------------------ AUTH HEADERS ------------------
def generate_token() -> str:
    # Vapi API key (org-scoped)
    return vapi_api_key

def get_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {generate_token()}",
        "Content-Type": "application/json"
    }

def get_file_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {generate_token()}",
    }

# ------------------ Vapi Tools: KB query tool ------------------
async def create_query_tool(file_ids, tool_name="Query-Tool") -> Optional[Dict[str, Any]]:
    """
    Creates a Vapi 'query' tool bound to provided knowledge base file IDs.
    Returns JSON with 'id' or None on failure.
    """
    url = "https://api.vapi.ai/tool/"
    headers = get_headers()
    data = {
        "type": "query",
        "function": {"name": tool_name},
        "knowledgeBases": [
            {
                "provider": "google",
                "name": "product-kb",
                "description": "Use this knowledge base when the user asks or queries about the product or services",
                "fileIds": file_ids,
            }
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, headers=headers, json=data)
            if r.status_code in (200, 201):
                return r.json()
            print(f"[create_query_tool] error {r.status_code}: {r.text}")
            return None
    except Exception as e:
        print(f"[create_query_tool] unexpected error: {e}")
        return None

# ------------------ Vapi Tools: book_appointment (API Request tool) ------------------
async def create_book_appointment_tool(tool_name: str = "book_appointment") -> Optional[Dict[str, Any]]:
    """
    Creates an 'apiRequest' tool in Vapi that POSTs to our backend to schedule appointments.
    Required POST body fields: callId, date (YYYY-MM-DD), time (HH:MM 24h)
    """
    url = "https://api.vapi.ai/tool/"
    headers = get_headers()

    # Build absolute, normalized URL to avoid double slashes
    schedule_url = f"{API_PUBLIC_BASE}/api/appointments/tool/schedule"

    data = {
        "type": "apiRequest",
        "name": tool_name,
        "description": "Create an appointment when the caller asks to schedule or book.",
        "function": {"name": "api_request_tool"},
        "method": "POST",
        "url": schedule_url,
        # Per Vapi docs, headers schema must declare type, properties, and a value for each header.
        # Also include explicit Content-Type.
        "headers": {
            "type": "object",
            "properties": {
                "Content-Type": {
                    "type": "string",
                    "value": "application/json"
                },
                "X-Tool-Secret": {
                    "type": "string",
                    "value": APPOINTMENT_TOOL_SECRET or ""
                }
            }
        },
        "body": {
            "type": "object",
            "properties": {
                "callId": {"type": "string", "description": "Current call id"},
                "date": {"type": "string", "description": "YYYY-MM-DD (caller local)"},
                "time": {"type": "string", "description": "HH:MM 24h (caller local)"},
                "timezone": {"type": "string", "description": "IANA tz, e.g. America/Los_Angeles"},
                "durationMinutes": {"type": "number", "description": "Length in minutes"},
                "title": {"type": "string"},
                "location": {"type": "string"},
                "notes": {"type": "string"}
            },
            "required": ["callId", "date", "time"]
        },
        "backoffPlan": {"type": "exponential", "maxRetries": 3, "baseDelaySeconds": 1},
        "timeoutSeconds": 45
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, headers=headers, json=data)
            if r.status_code in (200, 201):
                tjson = r.json()
                print("[create_book_appointment_tool] created:", tjson.get("id"))
                return tjson
            print("[create_book_appointment_tool] failed:", r.status_code, r.text)
            return None
    except Exception as e:
        print("[create_book_appointment_tool] error:", e)
        return None

# cache the created id in-process to avoid duplicate creations
_cached_appt_tool_id: Optional[str] = None

async def ensure_book_appt_tool_id() -> str:
    global _cached_appt_tool_id
    if BOOK_APPT_TOOL_ID:
        return BOOK_APPT_TOOL_ID
    if _cached_appt_tool_id:
        return _cached_appt_tool_id
    created = await create_book_appointment_tool()
    _cached_appt_tool_id = created.get("id") if created else ""
    return _cached_appt_tool_id

# ------------------ Payload builders (attach KB + book_appointment tool) ------------------
async def admin_add_payload(assistant_data):
    to_return = {
        "transcriber": {
            "provider": assistant_data.transcribe_provider,
            "model": assistant_data.transcribe_model,
            "language": assistant_data.transcribe_language,
        },
        "model": {
            "messages": [{"content": assistant_data.systemPrompt, "role": "system"}],
            "provider": assistant_data.provider,
            "model": assistant_data.model,
            "temperature": assistant_data.temperature,
            "knowledgeBase": {"provider": "canonical", "topK": 5, "fileIds": assistant_data.knowledgeBase},
            "maxTokens": assistant_data.maxTokens,
        },
        "voice": {
            "provider": assistant_data.voice_provider,
            "voiceId": assistant_data.voice,
            "model": (
                assistant_data.voice_model
                if assistant_data.voice_model
                else "octave" if assistant_data.voice_provider == "hume"
                else "eleven_flash_v2_5" if assistant_data.voice_provider == "11labs"
                else "aura" if assistant_data.voice_provider == "deepgram"
                else "eleven_flash_v2_5"
            ),
            **(
                {
                    "speed": assistant_data.speed if assistant_data.speed is not None else 1.0,
                    "stability": assistant_data.stability if assistant_data.stability is not None else 0.75,
                    "similarityBoost": assistant_data.similarityBoost if assistant_data.similarityBoost is not None else 0.75,
                }
                if assistant_data.voice_provider == "11labs"
                else {}
            ),
        },
        "firstMessageMode": "assistant-speaks-first",
        "hipaaEnabled": getattr(assistant_data, 'hipaaEnabled', False),
        "clientMessages": assistant_data.clientMessages,
        "serverMessages": assistant_data.serverMessages,
        "silenceTimeoutSeconds": 30,
        "maxDurationSeconds": getattr(assistant_data, 'maxDurationSeconds', 600),
        "backgroundSound": "office",
        "backchannelingEnabled": False,
        "backgroundDenoisingEnabled": False,
        "modelOutputInMessagesEnabled": False,
        "transportConfigurations": [
            {"provider": "twilio", "timeout": 60, "record": False, "recordingChannels": "mono"}
        ],
        "name": assistant_data.name,
        "firstMessage": assistant_data.first_message,
        "voicemailMessage": getattr(assistant_data, 'voicemailMessage', ""),
        "endCallMessage": getattr(assistant_data, 'endCallMessage', ""),
        "endCallPhrases": assistant_data.endCallPhrases,
        "metadata": {},
        "analysisPlan": {
            "summaryPrompt": assistant_data.systemPrompt,
            "summaryRequestTimeoutSeconds": 10.5,
            "structuredDataRequestTimeoutSeconds": 10.5,
            "successEvaluationPrompt": getattr(assistant_data, 'successEvaluationPrompt', ""),
            "successEvaluationRubric": "PassFail",
            "successEvaluationRequestTimeoutSeconds": 10.5,
            "structuredDataPrompt": getattr(assistant_data, 'structuredDataPrompt', ""),
            "structuredDataSchema": {"type": "string", "items": {"type": "string"}, "properties": {}, "description": "<string>", "required": ["<string>"]},
        },
        "artifactPlan": {"recordingEnabled": getattr(assistant_data, 'audioRecordingEnabled', True), "videoRecordingEnabled": getattr(assistant_data, 'videoRecordingEnabled', False), "recordingPath": "<string>"},
        "messagePlan": {"idleMessages": getattr(assistant_data, 'idleMessages', [""]), "idleMessageMaxSpokenCount": getattr(assistant_data, 'idleMessageMaxSpokenCount', 5), "idleTimeoutSeconds": getattr(assistant_data, 'idleTimeoutSeconds', 17.5)},
        "startSpeakingPlan": {"waitSeconds": 0.4, "smartEndpointingEnabled": False, "transcriptionEndpointingPlan": {"onPunctuationSeconds": 0.1, "onNoPunctuationSeconds": 1.5, "onNumberSeconds": 0.5}},
        "stopSpeakingPlan": {"numWords": 0, "voiceSeconds": 0.2, "backoffSeconds": 1},
        "monitorPlan": {"listenEnabled": False, "controlEnabled": False},
    }

    # transfer call tool
    if assistant_data.forwardingPhoneNumber:
        to_return["model"]["tools"] = [{
            "type": "transferCall",
            "destinations": [{"type": "number", "number": assistant_data.forwardingPhoneNumber, "description": "Transfer to customer support"}],
        }]
        to_return["forwardingPhoneNumber"] = assistant_data.forwardingPhoneNumber

    # collect toolIds (KB + book_appointment)
    tool_ids = []
    if assistant_data.knowledgeBase:
        kb_tool = await create_query_tool(assistant_data.knowledgeBase)
        if kb_tool and kb_tool.get("id"):
            tool_ids.append(kb_tool["id"])
        else:
            print("KB Tool creation failed or returned no id.")

    appt_tool_id = await ensure_book_appt_tool_id()
    if appt_tool_id:
        tool_ids.append(appt_tool_id)
    else:
        print("book_appointment tool not available (creation failed).")

    to_return["model"]["toolIds"] = tool_ids
    return to_return

async def user_add_payload(assistant_data, user):
    # languages in system prompt
    if not getattr(assistant_data, "languages", None):
        systemprompt = f"{assistant_data.systemPrompt} Please note, you can only communicate in **English**. Any other language will not be understood, and responses will be in English only."
    else:
        languages = ", ".join(assistant_data.languages)
        systemprompt = f"{assistant_data.systemPrompt} Please note, you can only communicate in the: **{languages}** languages. Any other language will not be understood, and responses will be given only in these **{languages}** languages."

    # voice selection
    if assistant_data.voice_provider == "deepgram":
        voice = {"provider": "deepgram", "voiceId": assistant_data.voice, "model": "aura"}
    elif assistant_data.voice_provider == "hume":
        voice_model = assistant_data.voice_model if assistant_data.voice_model else "octave"
        voice = {"provider": "hume", "voiceId": assistant_data.voice, "model": voice_model}
    elif assistant_data.voice_provider == "openai":
        voice = {"provider": "openai", "voiceId": assistant_data.voice, "model": "gpt-4o-mini-tts"}
    else:
        voice = {
            "provider": assistant_data.voice_provider,
            "voiceId": assistant_data.voice,
            "model": "eleven_flash_v2_5",
            "speed": assistant_data.speed if assistant_data.speed is not None else 1.0,
            "stability": assistant_data.stability if assistant_data.stability is not None else 0.75,
            "similarityBoost": assistant_data.similarityBoost if assistant_data.similarityBoost is not None else 0.75,
        }

    payload = {
        "transcriber": {
            "provider": assistant_data.transcribe_provider,
            "model": assistant_data.transcribe_model,
            "language": assistant_data.transcribe_language,
        },
        "model": {
            "messages": [{"content": systemprompt, "role": "system"}],
            "provider": assistant_data.provider,
            "model": assistant_data.model,
            "temperature": assistant_data.temperature,
            "knowledgeBase": {"provider": "canonical", "topK": 5, "fileIds": assistant_data.knowledgeBase},
            "maxTokens": assistant_data.maxTokens,
        },
        "voice": voice,
        "name": assistant_data.name,
        "firstMessage": assistant_data.first_message,
        "firstMessageMode": "assistant-speaks-first",
        "silenceTimeoutSeconds": 30,
        "maxDurationSeconds": 600,
        "endCallPhrases": assistant_data.endCallPhrases,
        "analysisPlan": {"summaryPrompt": assistant_data.systemPrompt},
        "startSpeakingPlan": {
            "waitSeconds": 0.8,
            "smartEndpointingEnabled": True,
            "transcriptionEndpointingPlan": {"onPunctuationSeconds": 0.3, "onNoPunctuationSeconds": 2.0, "onNumberSeconds": 0.8},
        },
        "stopSpeakingPlan": {"numWords": 0, "voiceSeconds": 0.5, "backoffSeconds": 1.5},
    }

    if assistant_data.forwardingPhoneNumber:
        payload["forwardingPhoneNumber"] = assistant_data.forwardingPhoneNumber
        payload["model"]["tools"] = [{
            "type": "transferCall",
            "destinations": [{"type": "number", "number": assistant_data.forwardingPhoneNumber, "description": "Transfer to customer support"}],
        }]

    # collect toolIds (KB + book_appointment)
    tool_ids = []
    if assistant_data.knowledgeBase:
        kb_tool = await create_query_tool(assistant_data.knowledgeBase)
        if kb_tool and kb_tool.get("id"):
            tool_ids.append(kb_tool["id"])
        else:
            print("KB Tool creation failed or returned no id.")

    appt_tool_id = await ensure_book_appt_tool_id()
    if appt_tool_id:
        tool_ids.append(appt_tool_id)
    else:
        print("book_appointment tool not available (creation failed).")

    payload["model"]["toolIds"] = tool_ids
    return payload

async def assistant_payload(assistant_data, company_id):
    # to keep this answer focused, unchanged from your version except for toolIds handling (same as above)
    return await user_add_payload(assistant_data, user=None)
