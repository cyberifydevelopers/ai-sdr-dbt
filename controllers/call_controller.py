import asyncio
import os
from datetime import date
from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
import httpx
from helpers.token_helper import get_current_user
from helpers.get_user_admin import get_user_admin
from helpers.get_user_admin import get_user_admin
# from helpers.send_email import send_dnc_email
from helpers.vapi_helper import generate_token, get_headers
import requests

from models.auth import User
from models.call_log import CallLog

from datetime import datetime
from tortoise.expressions import Q
from fastapi import Request
from models.assistant import Assistant

router = APIRouter()
token = generate_token()

# //////////////////////////////////////  Call Logs History from database  /////////////////////////////////////////
@router.get("/all_call_logs")
async def get_logs(user: Annotated[User, Depends(get_current_user)]):
    return await CallLog.all()
    
# //////////////////////////////////////  user specific Call Logs History from database  /////////////////////////////////////////
@router.get("/user/call-logs") 
async def get_user_call_logs(user: Annotated[User, Depends(get_current_user)],
):
    try:
        call_logs = await CallLog.filter(user=user).prefetch_related("user").all()
        
        if not call_logs:
            return []
        
        return [{"id": log.id,
                 "call_id": log.call_id,
                 "call_started_at": log.call_started_at.isoformat() if log.call_started_at else None,
                 "call_ended_at": log.call_ended_at.isoformat() if log.call_ended_at else None,
                 "cost": str(log.cost) if log.cost else None,
                 "customer_number": log.customer_number,
                 "customer_name": log.customer_name,
                 "call_ended_reason": log.call_ended_reason,
                 "lead_id":log.lead_id
                } for log in call_logs]

    except Exception as e:
        print("An error occurred while retrieving call logs:")
        print(str(e))
        raise HTTPException(status_code=400, detail=f"{str(e)}")
    
#/////////////////////////////////////////////////  Call Logs from database  /////////////////////////////////////////
@router.get("/user/call-logs-detail") 
async def get_user_call_logs(user: Annotated[User, Depends(get_current_user)]):
    try:
        call_logs = await CallLog.filter(user=user.id).prefetch_related("user").all().order_by("-id")
        
        if not call_logs:  
            return []
        
        return call_logs

    except Exception as e:
        print("An error occurred while retrieving call logs:")
        print(str(e))
        raise HTTPException(status_code=400, detail=f"{str(e)}")
    

#/////////////////////////////////////////////////  number Call Logs from database  /////////////////////////////////////////
@router.get("/specific-number-call-logs/{phoneNumber}")
async def call_details(phoneNumber: str, user:Annotated[User, Depends(get_current_user)]):
    try:
        print("phoneNumber",phoneNumber)
        call_details = await CallLog.filter(user=user.id, customer_number = phoneNumber).all()
        if not call_details:
           return []
        return call_details
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"{str(e)}")


@router.get("/user/call-cost") 
async def get_user_call_logs(user: Annotated[User, Depends(get_current_user)], 
):
    try:
        call_logs = await CallLog.filter(user=user).prefetch_related("user").all()
        
        if not call_logs:
            return []
        
        return call_logs

    except Exception as e:
        print("An error occurred while retrieving call logs:")
        print(str(e))
        raise HTTPException(status_code=400, detail=f"An error occurred: {str(e)}")
    


@router.get("/call/{call_id}")
async def get_call(call_id: str,user: Annotated[User, Depends(get_current_user)]):
    print("567898yui9")
    try:
        call_detail_url = f"https://api.vapi.ai/call/{call_id}" 
        response = requests.get(call_detail_url, headers=get_headers())
       
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to retrieve call details")

        call_data = response.json()
        # print("call_data",call_data)
        started_at = call_data.get("startedAt", None)
        ended_at = call_data.get("endedAt", None)
        print("call started at ",started_at)
        print("call ended at ",ended_at)



        call_duration = None
        if started_at and ended_at:
            start_time = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            end_time = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))

            call_duration = (end_time - start_time).total_seconds()
        # success_evalution= call_data.get("analysis", {}).get("successEvaluation")
        important_info = {
            "recording_url": call_data.get("artifact", {}).get("recordingUrl", "N/A"),
            "transcript": call_data.get("artifact", {}).get("transcript", "No transcript available"),
            "ended_reason": call_data.get("endedReason", "Unknown"),
            "status": call_data.get("status", "Unknown"),
            "call_ended_at":call_data.get("endedAt", None),
            "call_started_at":call_data.get("startedAt", None),
            "cost": call_data.get("cost", 0),
            "created_at": call_data.get("createdAt", "Unknown"),
            "updated_at": call_data.get("updatedAt", "Unknown"),
            "call_duration": call_duration,  
            "assistant": {
                "id": call_data.get("assistantId", "Unknown"),
                "name": call_data.get("assistant", {}).get("name", "Unknown assistant"),
            },
            "variableValues": { 
                "name": call_data.get("assistantOverrides", {}).get("variableValues", {}).get("name", "Unknown"),
                "email": call_data.get("assistantOverrides", {}).get("variableValues", {}).get("email", "Unknown"),
                "mobile_no": call_data.get("assistantOverrides", {}).get("variableValues", {}).get("mobile_no", "Unknown"),
                "add_date": call_data.get("assistantOverrides", {}).get("variableValues", {}).get("add_date", "Unknown"),
                "custom_field_01": call_data.get("assistantOverrides", {}).get("variableValues", {}).get("custom_field_01", "Unknown"),
                "custom_field_02": call_data.get("assistantOverrides", {}).get("variableValues", {}).get("custom_field_02", "Unknown"),
            },
            "summary": call_data.get("analysis", {}).get("summary", "N/A"),
            # "successEvalution": success_evalution
        }
        # call = await CallLog.get_or_none(call_id = call_id)
        # # time_left = await TimeLimit.filter(user=user).first()
        # if call:
        #      call.call_ended_reason = call_data.get("endedReason", "Unknown")
        #      call.cost = call_data.get("cost", 0)
        #      call.status = call_data.get("status", "Unknown")
        #      call.call_duration = call_duration
        #      await call.save()
        # else:
        #     await CallLog.create(
        #      call_id=call_id,
        #      call_ended_reason=call_data.get("endedReason", "Unknown"),
        #      cost=call_data.get("cost", 0),
        #      status=call_data.get("status", "Unknown"),
        #  )
        
        # time_left.seconds = time_left.seconds - call_duration
        # await time_left.save()
                    
        return important_info

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


    
@router.delete("/call_log/{id}")
async def delete_calls(id:str):
    try:
        url = f"https://api.vapi.ai/call/{id}"
        headers = {
            "Authorization" :f"Bearer {token}"
        }
        response = requests.request("DELETE", url, headers=headers)
        if response.status_code not in [200, 204]:
                raise HTTPException(
                    status_code=400, 
                    detail=f"VAPI phone number detachment failed with status {response.status_code}: {response.text}"
                )
        await CallLog.filter(call_id=id).delete()
        return{"success":True, "detail" : "Call log delted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500,detail=f"Error Fetching Call logs: {str(e)}")
    

@router.get("/update_calls")
async def update_call_logs_for_missing_details():
    try:        
        calls_to_update = await CallLog.filter(
            Q(call_ended_reason__isnull=True) | Q(call_duration__isnull=True)
        ).all()
        
        if not calls_to_update:
            print("No calls need to be updated.")
            return {"message": "No calls need to be updated."}
        
        updated_count = 0
        
        for call in calls_to_update:
            call_id = call.call_id
            print(f"Fetching details for call: {call_id}")
            
            call_detail_url = f"https://api.vapi.ai/call/{call_id}"
            async with httpx.AsyncClient() as client:
                response = await client.get(call_detail_url, headers=get_headers())
            
            if response.status_code != 200:
                print(f"Failed to retrieve details for call {call_id}, status code {response.status_code}")
                continue  
                
            call_data = response.json()
            started_at = call_data.get("startedAt", None)
            ended_at = call_data.get("endedAt", None)
            call_ended_reason = call_data.get("endedReason", "Unknown")
            cost = call_data.get("cost", 0)
            status = call_data.get("status", "Unknown")
            transcript = call_data.get("artifact", {}).get("transcript", "No transcript available")
            
            call_duration = None
            if started_at and ended_at:
                try:
                    start_time = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                    end_time = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
                    call_duration = (end_time - start_time).total_seconds()
                except ValueError as date_error:
                    print(f"Error parsing dates for call {call_id}: {date_error}")
                    call_duration = 0
            
            call.call_ended_reason = call_ended_reason
            call.cost = cost
            call.status = status
            call.call_duration = call_duration if call_duration else 0
            
            if ended_at:
                try:
                    call.call_ended_at = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
                except ValueError as date_error:
                    print(f"Error parsing end date for call {call_id}: {date_error}")
                    call.call_ended_at = None
            
            await call.save()
            updated_count += 1
            print(f"Successfully updated call {call_id}")
            
        return {"message": f"Successfully updated {updated_count} calls"}
        
    except Exception as e:
        print(f"Error in update_call_logs_for_missing_details: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# async def get_call_details(call_id: str, delay: int ,user_id :int, lead_id : Optional[int] = None ):
#     print("background task-----------------------")
#     try:
#         await asyncio.sleep(delay)
#         print(f"Starting call details retrieval after {delay} seconds delay")
        
#         # Enhanced retry logic for long calls
#         max_retries = 5  # Increased from 3 to 5 for long calls
#         base_retry_delay = 120  # 2 minutes base delay between retries
#         progressive_delay = True  # Increase delay progressively
        
#         for attempt in range(max_retries):
#             # Progressive delay: 2min, 4min, 6min, 8min, 10min
#             if progressive_delay and attempt > 0:
#                 retry_delay = base_retry_delay * (attempt + 1)
#             else:
#                 retry_delay = base_retry_delay
                
#             print(f"Attempt {attempt + 1}/{max_retries} - Retry delay: {retry_delay} seconds")
            
#             call_detail_url = f"https://api.vapi.ai/call/{call_id}"
#             async with httpx.AsyncClient() as client:
#                 response = await client.get(call_detail_url, headers=get_headers())
            
#             if response.status_code != 200:
#                 print(f"Failed to retrieve call details, status: {response.status_code}")
#                 if attempt < max_retries - 1:
#                     print(f"Retrying in {retry_delay} seconds...")
#                     await asyncio.sleep(retry_delay)
#                     continue
#                 else:
#                     raise HTTPException(status_code=response.status_code, detail="Failed to retrieve call details")

#             call_data = response.json()
#             started_at = call_data.get("startedAt", None)
#             ended_at = call_data.get("endedAt", None)
#             print(f"Call started: {started_at}")
#             print(f"Call ended: {ended_at}")
            
#             # Calculate actual call duration
#             call_duration = None
#             if started_at and ended_at:
#                 start_time = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
#                 end_time = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
#                 call_duration = (end_time - start_time).total_seconds()
#                 print(f"Actual call duration: {call_duration} seconds ({call_duration/60:.1f} minutes)")
            
#             transcript = call_data.get("artifact", {}).get("transcript", "No transcript available")
#             recording_url = call_data.get("artifact", {}).get("recordingUrl", "N/A")
            
#             # Enhanced transcript validation for long calls
#             transcript_quality = "incomplete"
#             if transcript and transcript != "No transcript available":
#                 word_count = len(transcript.split())
#                 sentence_count = len(transcript.split('.'))
                
#                 # For long calls, expect more content
#                 if call_duration and call_duration > 1800:  # > 30 minutes
#                     min_words = int(call_duration / 60 * 10)  # ~10 words per minute
#                     min_sentences = int(call_duration / 60 * 2)  # ~2 sentences per minute
#                 else:
#                     min_words = 50
#                     min_sentences = 10
                
#                 print(f"Transcript stats - Words: {word_count}, Sentences: {sentence_count}")
#                 print(f"Expected minimum - Words: {min_words}, Sentences: {min_sentences}")
                
#                 if word_count >= min_words and sentence_count >= min_sentences:
#                     transcript_quality = "complete"
#                     print(f"Complete transcript found on attempt {attempt + 1}")
#                     break
#                 else:
#                     transcript_quality = "partial"
#                     print(f"Partial transcript on attempt {attempt + 1} - Quality: {transcript_quality}")
#             else:
#                 print(f"No transcript available on attempt {attempt + 1}")
            
#             # Progressive delay for next attempt
#             if attempt < max_retries - 1:
#                 print(f"Transcript incomplete, retrying in {retry_delay} seconds...")
#                 await asyncio.sleep(retry_delay)
#             else:
#                 print("Max retries reached, using available transcript")
        
#         # Process call data
#         user = await User.filter(id=user_id).first()
        
#         call = await CallLog.get_or_none(call_id=call_id)
#         if call:
#             print(f"Updating existing call log for call ID: {call_id}")
#             print(f"Call duration: {call_duration} seconds")
#             print(f"Call ended reason: {call_data.get('endedReason', 'Unknown')}")

#             call.is_transferred = False
#             call.call_ended_reason = call_data.get("endedReason", "Unknown")
#             call.cost = call_data.get("cost", 0)
#             call.status = call_data.get("status", "Unknown")
#             call.call_duration = call_duration if call_duration else 0
#             call.criteria_satisfied = False
            
#             if isinstance(ended_at, str):
#                 call.call_ended_at = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
#             else:
#                 call.call_ended_at = ended_at
                
#             await call.save()
            
#             # Enhanced debug logging for long calls
#             print("🔊 [CALL ENDED] ENHANCED DEBUG INFO:")
#             print(f"🔊 [CALL ENDED] Call ID: {call_id}")
#             print(f"🔊 [CALL ENDED] Call Duration: {call_duration} seconds ({call_duration/60:.1f} minutes)")
#             print(f"🔊 [CALL ENDED] Call Status: {call_data.get('status', 'Unknown')}")
#             print(f"🔊 [CALL ENDED] Call Ended Reason: {call_data.get('endedReason', 'Unknown')}")
#             print(f"🔊 [CALL ENDED] Call Cost: {call_data.get('cost', 0)}")
#             print(f"🔊 [CALL ENDED] Transcript Quality: {transcript_quality}")
#             print(f"🔊 [CALL ENDED] Transcript Length: {len(transcript) if transcript else 0} characters")
#             print(f"🔊 [CALL ENDED] Recording URL: {recording_url}")
#             if transcript:
#                 print(f"🔊 [CALL ENDED] Transcript Preview: {transcript[:300]}...")

#         else:
#             print(f"Creating new call log for call ID: {call_id}")
            
#             new_call_log = await CallLog.create(
#                 is_transferred = False,
#                 call_id=call_id,
#                 call_ended_reason=call_data.get("endedReason", "Unknown"),
#                 cost=call_data.get("cost", 0),
#                 status=call_data.get("status", "Unknown"),
#                 call_ended_at=datetime.fromisoformat(ended_at.replace("Z", "+00:00")) if isinstance(ended_at, str) else ended_at,
#                 call_duration=call_duration,
#                 criteria_satisfied = False
#             )
            
#             # Enhanced debug logging for new call logs
#             print("🔊 [CALL ENDED] ENHANCED DEBUG INFO (NEW LOG):")
#             print(f"🔊 [CALL ENDED] Call ID: {call_id}")
#             print(f"🔊 [CALL ENDED] Call Duration: {call_duration} seconds ({call_duration/60:.1f} minutes)")
#             print(f"🔊 [CALL ENDED] Call Status: {call_data.get('status', 'Unknown')}")
#             print(f"🔊 [CALL ENDED] Call Ended Reason: {call_data.get('endedReason', 'Unknown')}")
#             print(f"🔊 [CALL ENDED] Call Cost: {call_data.get('cost', 0)}")
#             print(f"🔊 [CALL ENDED] Transcript Quality: {transcript_quality}")
#             print(f"🔊 [CALL ENDED] Transcript Length: {len(transcript) if transcript else 0} characters")
#             print(f"🔊 [CALL ENDED] Recording URL: {recording_url}")
#             if transcript:
#                 print(f"🔊 [CALL ENDED] Transcript Preview: {transcript[:300]}...")

#     except Exception as e:
#         print(f"Error in get_call_details: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")







# helpers/vapi_helper.py
import os
import jwt
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pytz
import httpx
import asyncio
from models.auth import User

# some projects reference AssignedLanguage here; keep this safe-import
try:
    from models.assigned_language import AssignedLanguage
except Exception:
    AssignedLanguage = None  # will only matter if assistant_payload uses it

load_dotenv()

# ------------------ ENV ------------------
vapi_api_key = os.environ["VAPI_API_KEY"]
vapi_org_id = os.environ.get("VAPI_ORG_ID", "")

# where your API is publicly reachable (ngrok)
API_PUBLIC_BASE = os.getenv("API_PUBLIC_BASE", "https://c57a8e025f6a.ngrok-free.app")
# shared secret used by the Vapi tool → your backend
APPOINTMENT_TOOL_SECRET = os.getenv("APPOINTMENT_TOOL_SECRET", "change-me")
# if you already created the tool manually in Vapi UI, you can pin it here
BOOK_APPT_TOOL_ID = os.getenv("BOOK_APPT_TOOL_ID", "")

# Debug: Check if environment variables are loaded correctly
print("VAPI_API_KEY:", os.getenv("VAPI_API_KEY"))
print("VAPI_ORG_ID:", os.getenv("VAPI_ORG_ID"))
print("API_PUBLIC_BASE:", API_PUBLIC_BASE)
print("BOOK_APPT_TOOL_ID:", BOOK_APPT_TOOL_ID)
print ("APPOINTMENT_TOOL_SECRET" , APPOINTMENT_TOOL_SECRET)
# ------------------ AUTH HEADERS ------------------
def generate_token():
    # For Vapi, using the API key as bearer works for org-scoped calls
    return vapi_api_key

def get_headers():
    token = generate_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

def get_file_headers():
    token = generate_token()
    return {
        "Authorization": f"Bearer {token}",
    }

# ------------------ Vapi Tools: KB query tool (YOURS, unchanged) ------------------
async def create_query_tool(file_ids, tool_name="Query-Tool"):
    """
    Creates a Vapi 'query' tool bound to provided knowledge base file IDs.
    Returns JSON with 'id' or None on failure.
    """
    url = "https://api.vapi.ai/tool/"
    headers = {
        "Authorization": f"Bearer {vapi_api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "type": "query",
        "function": {"name": tool_name},
        "knowledgeBases": [
            {
                "provider": "google",
                "name": "product-kb",
                "description": "Use this knowledge base when the user asks or queries about the product or services",
                "fileIds": file_ids
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=data)
            if response.status_code in [200, 201]:
                return response.json()
            else:
                print(f"[create_query_tool] error {response.status_code}: {response.text}")
                return None
    except httpx.RequestError as e:
        print(f"[create_query_tool] request error: {e}")
        return None
    except Exception as e:
        print(f"[create_query_tool] unexpected error: {e}")
        return None

# ------------------ Vapi Tools: book_appointment (NEW) ------------------
async def create_book_appointment_tool(tool_name: str = "book_appointment"):
    """
    Creates an 'apiRequest' tool in Vapi that posts to our backend to schedule appointments.

    Body schema the LLM will fill:
    - callId (string) REQUIRED
    - date (string, YYYY-MM-DD) REQUIRED
    - time (string, HH:MM 24h) REQUIRED
    - timezone (string, IANA tz)
    - durationMinutes (number)
    - title (string)
    - location (string)
    - notes (string)
    """
    url = "https://api.vapi.ai/tool/"
    headers = {
        "Authorization": f"Bearer {vapi_api_key}",
        "Content-Type": "application/json",
    }

    data = {
        "type": "apiRequest",
        "name": tool_name,
        "description": "Create an appointment when the caller asks to schedule.",
        "function": {"name": "api_request_tool"},
        "method": "POST",
        "url": f"{API_PUBLIC_BASE}/api/appointments/tool/schedule",
        # Send a shared secret with the request so your backend can verify Vapi
        "headers": {
            "type": "object",
            "properties": {
                "X-Tool-Secret": {
                    "type": "string",
                    "value": APPOINTMENT_TOOL_SECRET
                }
            }
        },
        # JSON schema that the LLM uses to construct the POST body
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

async def ensure_book_appt_tool_id() -> str:
    """
    Returns a tool id for book_appointment.
    If BOOK_APPT_TOOL_ID is set in env, use that; otherwise try to create one.
    """
    if BOOK_APPT_TOOL_ID:
        return BOOK_APPT_TOOL_ID
    created = await create_book_appointment_tool()
    return created.get("id") if created else ""

# ------------------ Payload builders (UPDATED to attach book_appointment tool) ------------------
async def admin_add_payload(assistant_data):
    """
    Admin-facing assistant payload.
    Attaches KB tool (if any) and the book_appointment tool.
    """
    print(assistant_data)
    to_return = {
        "transcriber": {
            "provider": assistant_data.transcribe_provider,
            "model": assistant_data.transcribe_model,
            "language": assistant_data.transcribe_language,
        },
        "model": {
            "messages": [
                {
                    "content": assistant_data.systemPrompt,
                    "role": "system"
                }
            ],
            "provider": assistant_data.provider,
            "model": assistant_data.model,
            "temperature": assistant_data.temperature,
            "knowledgeBase": {
                "provider": "canonical",
                "topK": 5,
                "fileIds": assistant_data.knowledgeBase
            },
            "maxTokens": assistant_data.maxTokens,
        },
        "voice": {
            "provider": assistant_data.voice_provider,
            "voiceId": assistant_data.voice,
            "model": assistant_data.voice_model if assistant_data.voice_model else "octave" if assistant_data.voice_provider == "hume" else "eleven_flash_v2_5" if assistant_data.voice_provider == "11labs" else "aura" if assistant_data.voice_provider == "deepgram" else "eleven_flash_v2_5",
            **({"speed": assistant_data.speed if assistant_data.speed is not None else 1.0,
                "stability": assistant_data.stability if assistant_data.stability is not None else 0.75,
                "similarityBoost": assistant_data.similarityBoost if assistant_data.similarityBoost is not None else 0.75} if assistant_data.voice_provider == "11labs" else {})
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
            {
                "provider": "twilio",
                "timeout": 60,
                "record": False,
                "recordingChannels": "mono"
            }
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
            "structuredDataSchema": {
                "type": "string",
                "items": {"type": "string"},
                "properties": {},
                "description": "<string>",
                "required": ["<string>"]
            }
        },
        "artifactPlan": {
            "recordingEnabled": getattr(assistant_data, 'audioRecordingEnabled', True),
            "videoRecordingEnabled": getattr(assistant_data, 'videoRecordingEnabled', False),
            "recordingPath": "<string>"
        },
        "messagePlan": {
            "idleMessages": getattr(assistant_data, 'idleMessages', [""]),
            "idleMessageMaxSpokenCount": getattr(assistant_data, 'idleMessageMaxSpokenCount', 5),
            "idleTimeoutSeconds": getattr(assistant_data, 'idleTimeoutSeconds', 17.5)
        },
        "startSpeakingPlan": {
            "waitSeconds": 0.4,
            "smartEndpointingEnabled": False,
            "transcriptionEndpointingPlan": {
                "onPunctuationSeconds": 0.1,
                "onNoPunctuationSeconds": 1.5,
                "onNumberSeconds": 0.5
            }
        },
        "stopSpeakingPlan": {
            "numWords": 0,
            "voiceSeconds": 0.2,
            "backoffSeconds": 1
        },
        "monitorPlan": {
            "listenEnabled": False,
            "controlEnabled": False
        }
    }

    # transfer call tool (unchanged)
    if assistant_data.forwardingPhoneNumber:
        to_return["model"]["tools"] = [
            {
                "type": "transferCall",
                "destinations": [
                    {
                        "type": "number",
                        "number": assistant_data.forwardingPhoneNumber,
                        "description": "Transfer to customer support",
                    }
                ]
            }
        ]
        to_return["forwardingPhoneNumber"] = assistant_data.forwardingPhoneNumber

    # --- collect toolIds (KB + book_appointment) ---
    tool_ids = []

    # KB tool (optional)
    if assistant_data.knowledgeBase and len(assistant_data.knowledgeBase) > 0:
        kb_tool = await create_query_tool(assistant_data.knowledgeBase)
        if kb_tool and kb_tool.get("id"):
            tool_ids.append(kb_tool["id"])
        else:
            print("KB Tool creation failed or returned no id.")

    # Appointment tool
    appt_tool_id = await ensure_book_appt_tool_id()
    if appt_tool_id:
        tool_ids.append(appt_tool_id)
    else:
        print("book_appointment tool not available (creation failed).")

    to_return["model"]["toolIds"] = tool_ids
    return to_return

async def user_add_payload(assistant_data, user):
    """
    User-facing assistant payload.
    Attaches KB tool (if any) and the book_appointment tool.
    """
    user = await User.filter(id=user.id).first()

    if not getattr(assistant_data, "languages", None):
        systemprompt = f"{assistant_data.systemPrompt} Please note, you can only communicate in **English**. Any other language will not be understood, and responses will be in English only."
    else:
        languages = ", ".join(assistant_data.languages)
        systemprompt = f"{assistant_data.systemPrompt} Please note, you can only communicate in the: **{languages}** languages. Any other language will not be understood, and responses will be given only in these **{languages}** languages."

    print(systemprompt)

    # voice selection (unchanged)
    if assistant_data.voice_provider == "deepgram":
        voice_model = "aura"
        voice = {
            "provider": assistant_data.voice_provider,
            "voiceId": assistant_data.voice,
            "model": voice_model,
        }
    elif assistant_data.voice_provider == "hume":
        voice_model = assistant_data.voice_model if assistant_data.voice_model else "octave"
        print(f"Hume voice configuration - voice_model: {voice_model}, voiceId: {assistant_data.voice}")
        voice = {
            "provider": assistant_data.voice_provider,
            "voiceId": assistant_data.voice,
            "model": voice_model,
        }
        print(f"Final Hume voice config: {voice}")
    elif assistant_data.voice_provider == "openai":
        voice = {
            "provider": "openai",
            "voiceId": assistant_data.voice,
            "model": "gpt-4o-mini-tts",
        }
        print(f"Final OpenAI voice config: {voice}")
    else:
        voice_model = "eleven_flash_v2_5"
        voice = {
            "provider": assistant_data.voice_provider,
            "voiceId": assistant_data.voice,
            "model": voice_model,
            "speed": assistant_data.speed if assistant_data.speed is not None else 1.0,
            "stability": assistant_data.stability if assistant_data.stability is not None else 0.75,
            "similarityBoost": assistant_data.similarityBoost if assistant_data.similarityBoost is not None else 0.75,
        }

    user_payload = {
        "transcriber": {
            "provider": assistant_data.transcribe_provider,
            "model": assistant_data.transcribe_model,
            "language": assistant_data.transcribe_language,
        },
        "model": {
            "messages": [
                {
                    "content": systemprompt,
                    "role": "system"
                }
            ],
            "provider": assistant_data.provider,
            "model": assistant_data.model,
            "temperature": assistant_data.temperature,
            "knowledgeBase": {
                "provider": "canonical",
                "topK": 5,
                "fileIds": assistant_data.knowledgeBase
            },
            "maxTokens": assistant_data.maxTokens,
        },
        "voice": voice,
        "name": assistant_data.name,
        "firstMessage": assistant_data.first_message,
        "firstMessageMode": "assistant-speaks-first",
        "silenceTimeoutSeconds": 30,
        "maxDurationSeconds": 600,
        "endCallPhrases": assistant_data.endCallPhrases,
        "analysisPlan": {
            "summaryPrompt": assistant_data.systemPrompt,
        },
        "startSpeakingPlan": {
            "waitSeconds": 0.8,
            "smartEndpointingEnabled": True,
            "transcriptionEndpointingPlan": {
                "onPunctuationSeconds": 0.3,
                "onNoPunctuationSeconds": 2.0,
                "onNumberSeconds": 0.8
            }
        },
        "stopSpeakingPlan": {
            "numWords": 0,
            "voiceSeconds": 0.5,
            "backoffSeconds": 1.5
        }
    }

    if assistant_data.forwardingPhoneNumber:
        user_payload["forwardingPhoneNumber"] = assistant_data.forwardingPhoneNumber
        user_payload["model"]["tools"] = [
            {
                "type": "transferCall",
                "destinations": [
                    {
                        "type": "number",
                        "number": assistant_data.forwardingPhoneNumber,
                        "description": "Transfer to customer support",
                    }
                ]
            }
        ]

    # --- collect toolIds (KB + book_appointment) ---
    tool_ids = []

    if assistant_data.knowledgeBase and len(assistant_data.knowledgeBase) > 0:
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

    user_payload["model"]["toolIds"] = tool_ids

    # Debug for Hume config (unchanged logs)
    if assistant_data.voice_provider == "hume":
        print(f"Final VAPI payload for Hume voice: {user_payload}")

    return user_payload

async def assistant_payload(assistant_data, company_id):
    """
    Company-context assistant payload.
    Attaches KB tool (if any) and the book_appointment tool.
    """
    # languages
    if AssignedLanguage:
        assigned_languages = await AssignedLanguage.filter(company_id=company_id).first()
    else:
        assigned_languages = None

    if assigned_languages and assigned_languages.language:
        if isinstance(assigned_languages.language, list):
            languages = ", ".join(assigned_languages.language)
        else:
            languages = assigned_languages.language
        systemprompt = f"{assistant_data.systemPrompt} Please note, you can only communicate in the : **{languages}** languages. Any other language will not be understood, and responses will be given only in these languages."
    else:
        systemprompt = f"{assistant_data.systemPrompt} Please note, you can only communicate in **English**. Any other language will not be understood, and responses will be in English only."

    # voice selection (unchanged)
    if assistant_data.voice_provider == "deepgram":
        voice_model = "aura"
        voice = {
            "provider": assistant_data.voice_provider,
            "voiceId": assistant_data.voice,
            "model": voice_model,
        }
    elif assistant_data.voice_provider == "hume":
        voice_model = assistant_data.voice_model if assistant_data.voice_model else "octave"
        print(f"Hume voice configuration - voice_model: {voice_model}, voiceId: {assistant_data.voice}")
        # validation logs...
        if not assistant_data.voice or len(assistant_data.voice) < 10:
            print(f"WARNING: Hume voice ID appears invalid: {assistant_data.voice}")
        uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
        is_valid_uuid = bool(uuid_pattern.match(assistant_data.voice)) if assistant_data.voice else False
        print(f"Hume voice ID UUID format check: {is_valid_uuid}")

        voice = {
            "provider": assistant_data.voice_provider,
            "voiceId": assistant_data.voice,
            "model": voice_model,
        }
        print(f"Final Hume voice config: {voice}")
    else:
        voice_model = "eleven_flash_v2_5"
        voice = {
            "provider": assistant_data.voice_provider,
            "voiceId": assistant_data.voice,
            "model": voice_model,
            "speed": assistant_data.speed or 0,
            "stability": assistant_data.stability,
            "similarityBoost": assistant_data.similarityBoost,
        }

    user_payload = {
        "transcriber": {
            "provider": assistant_data.transcribe_provider,
            "model": assistant_data.transcribe_model,
            "language": assistant_data.transcribe_language,
        },
        "model": {
            "messages": [
                {
                    "content": systemprompt,
                    "role": "system"
                }
            ],
            "provider": assistant_data.provider,
            "model": assistant_data.model,
            "temperature": assistant_data.temperature,
            "knowledgeBase": {
                "provider": "canonical",
                "topK": 5,
                "fileIds": assistant_data.knowledgeBase
            },
            "maxTokens": assistant_data.maxTokens,
        },
        "voice": voice,
        "name": assistant_data.name,
        "firstMessage": assistant_data.first_message,
        "firstMessageMode": "assistant-speaks-first",
        "silenceTimeoutSeconds": 30,
        "maxDurationSeconds": 600,
        "endCallPhrases": assistant_data.endCallPhrases,
        "analysisPlan": {
            "summaryPrompt": assistant_data.systemPrompt,
        },
        "startSpeakingPlan": {
            "waitSeconds": 0.8,
            "smartEndpointingEnabled": True,
            "transcriptionEndpointingPlan": {
                "onPunctuationSeconds": 0.3,
                "onNoPunctuationSeconds": 2.0,
                "onNumberSeconds": 0.8
            }
        },
        "stopSpeakingPlan": {
            "numWords": 0,
            "voiceSeconds": 0.5,
            "backoffSeconds": 1.5
        }
    }

    if assistant_data.forwardingPhoneNumber:
        user_payload["forwardingPhoneNumber"] = assistant_data.forwardingPhoneNumber
        user_payload["model"]["tools"] = [
            {
                "type": "transferCall",
                "destinations": [
                    {
                        "type": "number",
                        "number": assistant_data.forwardingPhoneNumber,
                        "description": "Transfer to customer support",
                    }
                ]
            }
        ]

    # --- collect toolIds (KB + book_appointment) ---
    tool_ids = []

    if assistant_data.knowledgeBase and len(assistant_data.knowledgeBase) > 0:
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

    user_payload["model"]["toolIds"] = tool_ids

    # optional additional logs
    print("assistant_payload toolIds:", tool_ids)

    return user_payload






async def get_call_details(call_id: str, delay: int, user_id: int, lead_id: Optional[int] = None):
    print("background task-----------------------")
    try:
        await asyncio.sleep(delay)
        print(f"Starting call details retrieval after {delay} seconds delay")
        
        # Enhanced retry logic for long calls
        max_retries = 5  # Increased from 3 to 5 for long calls
        base_retry_delay = 120  # 2 minutes base delay between retries
        progressive_delay = True  # Increase delay progressively
        
        for attempt in range(max_retries):
            # Progressive delay: 2min, 4min, 6min, 8min, 10min
            if progressive_delay and attempt > 0:
                retry_delay = base_retry_delay * (attempt + 1)
            else:
                retry_delay = base_retry_delay
                
            print(f"Attempt {attempt + 1}/{max_retries} - Retry delay: {retry_delay} seconds")
            
            call_detail_url = f"https://api.vapi.ai/call/{call_id}"
            async with httpx.AsyncClient() as client:
                response = await client.get(call_detail_url, headers=get_headers())
            
            if response.status_code != 200:
                print(f"Failed to retrieve call details, status: {response.status_code}")
                if attempt < max_retries - 1:
                    print(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    raise HTTPException(status_code=response.status_code, detail="Failed to retrieve call details")

            call_data = response.json()
            started_at = call_data.get("startedAt", None)
            ended_at = call_data.get("endedAt", None)
            print(f"Call started: {started_at}")
            print(f"Call ended: {ended_at}")
            
            # Calculate actual call duration
            call_duration = None
            if started_at and ended_at:
                start_time = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                end_time = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
                call_duration = (end_time - start_time).total_seconds()
                print(f"Actual call duration: {call_duration} seconds ({call_duration/60:.1f} minutes)")
            
            transcript = call_data.get("artifact", {}).get("transcript", "No transcript available")
            recording_url = call_data.get("artifact", {}).get("recordingUrl", "N/A")
            
            # Enhanced transcript validation for long calls
            transcript_quality = "incomplete"
            if transcript and transcript != "No transcript available":
                word_count = len(transcript.split())
                sentence_count = len(transcript.split('.'))
                
                # For long calls, expect more content
                if call_duration and call_duration > 1800:  # > 30 minutes
                    min_words = int(call_duration / 60 * 10)  # ~10 words per minute
                    min_sentences = int(call_duration / 60 * 2)  # ~2 sentences per minute
                else:
                    min_words = 50
                    min_sentences = 10
                
                print(f"Transcript stats - Words: {word_count}, Sentences: {sentence_count}")
                print(f"Expected minimum - Words: {min_words}, Sentences: {min_sentences}")
                
                if word_count >= min_words and sentence_count >= min_sentences:
                    transcript_quality = "complete"
                    print(f"Complete transcript found on attempt {attempt + 1}")
                    break
                else:
                    transcript_quality = "partial"
                    print(f"Partial transcript on attempt {attempt + 1} - Quality: {transcript_quality}")
            else:
                print(f"No transcript available on attempt {attempt + 1}")
            
            # Progressive delay for next attempt
            if attempt < max_retries - 1:
                print(f"Transcript incomplete, retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            else:
                print("Max retries reached, using available transcript")
        
        # Process call data
        user = await User.filter(id=user_id).first()
        
        call = await CallLog.get_or_none(call_id=call_id)
        if call:
            print(f"Updating existing call log for call ID: {call_id}")
            print(f"Call duration: {call_duration} seconds")
            print(f"Call ended reason: {call_data.get('endedReason', 'Unknown')}")

            call.is_transferred = False
            call.call_ended_reason = call_data.get("endedReason", "Unknown")
            call.cost = call_data.get("cost", 0)
            call.status = call_data.get("status", "Unknown")
            call.call_duration = call_duration if call_duration else 0
            call.criteria_satisfied = False
            
            if isinstance(ended_at, str):
                call.call_ended_at = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
            else:
                call.call_ended_at = ended_at
                
            await call.save()
            
            # Enhanced debug logging for long calls
            print("🔊 [CALL ENDED] ENHANCED DEBUG INFO:")
            print(f"🔊 [CALL ENDED] Call ID: {call_id}")
            print(f"🔊 [CALL ENDED] Call Duration: {call_duration} seconds ({call_duration/60:.1f} minutes)")
            print(f"🔊 [CALL ENDED] Call Status: {call_data.get('status', 'Unknown')}")
            print(f"🔊 [CALL ENDED] Call Ended Reason: {call_data.get('endedReason', 'Unknown')}")
            print(f"🔊 [CALL ENDED] Call Cost: {call_data.get('cost', 0)}")
            print(f"🔊 [CALL ENDED] Transcript Quality: {transcript_quality}")
            print(f"🔊 [CALL ENDED] Transcript Length: {len(transcript) if transcript else 0} characters")
            print(f"🔊 [CALL ENDED] Recording URL: {recording_url}")
            if transcript:
                print(f"🔊 [CALL ENDED] Transcript Preview: {transcript[:300]}...")

        else:
            print(f"Creating new call log for call ID: {call_id}")
            
            new_call_log = await CallLog.create(
                is_transferred = False,
                call_id=call_id,
                call_ended_reason=call_data.get("endedReason", "Unknown"),
                cost=call_data.get("cost", 0),
                status=call_data.get("status", "Unknown"),
                call_ended_at=datetime.fromisoformat(ended_at.replace("Z", "+00:00")) if isinstance(ended_at, str) else ended_at,
                call_duration=call_duration,
                criteria_satisfied = False
            )
            
            # Enhanced debug logging for new call logs
            print("🔊 [CALL ENDED] ENHANCED DEBUG INFO (NEW LOG):")
            print(f"🔊 [CALL ENDED] Call ID: {call_id}")
            print(f"🔊 [CALL ENDED] Call Duration: {call_duration} seconds ({call_duration/60:.1f} minutes)")
            print(f"🔊 [CALL ENDED] Call Status: {call_data.get('status', 'Unknown')}")
            print(f"🔊 [CALL ENDED] Call Ended Reason: {call_data.get('endedReason', 'Unknown')}")
            print(f"🔊 [CALL ENDED] Call Cost: {call_data.get('cost', 0)}")
            print(f"🔊 [CALL ENDED] Transcript Quality: {transcript_quality}")
            print(f"🔊 [CALL ENDED] Transcript Length: {len(transcript) if transcript else 0} characters")
            print(f"🔊 [CALL ENDED] Recording URL: {recording_url}")
            if transcript:
                print(f"🔊 [CALL ENDED] Transcript Preview: {transcript[:300]}...")

        # ------------------------------------------------------------------
        # 🔗 NEW: trigger appointment extraction via internal HTTP self-call
        # ------------------------------------------------------------------
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                await client.post(
                    f"{os.getenv('API_PUBLIC_BASE', 'http://localhost:8000')}/api/appointments/from-call/{call_id}",
                    headers={"Authorization": f"Bearer {generate_token()}"},
                )
            print("[Appointments] extraction triggered successfully.")
        except Exception as _e:
            print("appointment extract failed:", _e)

    except Exception as e:
        print(f"Error in get_call_details: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/refresh-transcript/{call_id}")
async def refresh_call_transcript(call_id: str, user: Annotated[User, Depends(get_current_user)]):
    """
    Manually refresh the transcript for a specific call
    Enhanced for long calls with better validation
    """
    try:
        call_detail_url = f"https://api.vapi.ai/call/{call_id}"
        async with httpx.AsyncClient() as client:
            response = await client.get(call_detail_url, headers=get_headers())
        
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to retrieve call details")

        call_data = response.json()
        transcript = call_data.get("artifact", {}).get("transcript", "No transcript available")
        recording_url = call_data.get("artifact", {}).get("recordingUrl", "N/A")
        
        # Calculate call duration for validation
        started_at = call_data.get("startedAt", None)
        ended_at = call_data.get("endedAt", None)
        call_duration = None
        if started_at and ended_at:
            start_time = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            end_time = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
            call_duration = (end_time - start_time).total_seconds()
        
        # Enhanced transcript validation
        transcript_quality = "not_available"
        word_count = 0
        sentence_count = 0
        
        if transcript and transcript != "No transcript available":
            word_count = len(transcript.split())
            sentence_count = len(transcript.split('.'))
            
            if call_duration and call_duration > 1800:  # > 30 minutes
                min_words = int(call_duration / 60 * 10)
                min_sentences = int(call_duration / 60 * 2)
            else:
                min_words = 50
                min_sentences = 10
            
            if word_count >= min_words and sentence_count >= min_sentences:
                transcript_quality = "complete"
            else:
                transcript_quality = "partial"
        
        # Update the call log with new transcript if available
        call_log = await CallLog.filter(call_id=call_id, user=user).first()
        if call_log:
            # You might want to add a transcript field to CallLog model
            # call_log.transcript = transcript
            # await call_log.save()
            pass
        
        return {
            "success": True,
            "transcript": transcript,
            "transcript_length": len(transcript) if transcript else 0,
            "transcript_quality": transcript_quality,
            "word_count": word_count,
            "sentence_count": sentence_count,
            "call_duration": call_duration,
            "call_duration_minutes": call_duration / 60 if call_duration else None,
            "recording_url": recording_url,
            "message": f"Transcript refreshed successfully. Quality: {transcript_quality}"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error refreshing transcript: {str(e)}")






async def analyze_call_transfer(transcript: str) -> dict:
    """
    Function to analyze the call transcript and determine if the conversation is between the AI agent
    and a human, or if the call was handled by a bot on the user's side. 
    Returns a dictionary with the result.
    """
    
    prompt = """
    Did the conversation start with the AI agent calling the user, and did the user pick up the call? 
    Based on the provided transcript, please determine if the conversation involves the AI agent speaking directly with the human user 
    or if an automated system (bot) responded on the user's side.

    If the conversation is between the AI agent and a human (user), just respond with: 
    isTransferred: True

    If a bot or automated system responded on the user's side instead of the user speaking directly, just respond with:
    isTransferred: False

    Transcript:
    {transcript}
    """
   
    # prompt_template = PromptTemplate(input_variables=["transcript"], template=prompt)
    
    # llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2, openai_api_key=open_ai_key)  
    # chain = LLMChain(llm=llm, prompt=prompt_template)
    
    # result = chain.run({"transcript": transcript})
    prompt = ChatPromptTemplate.from_template(prompt)
    model = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
    output_parser = StrOutputParser()
    chain = prompt | model | output_parser
    result = await chain.ainvoke({
        "transcript": transcript
    })
    
    is_transferred = "True" if "True" in result else "False"
    
    return {"isTransferred": is_transferred == "True"}


async def analyze_dnc(transcript: str, dnc_prompts: list) -> dict:
    """
    Analyze the call transcript to check if it matches DNC-related prompts using an LLM.
    
    Args:
        transcript (str): The call transcript.
        dnc_prompts (list): A list of DNC objects that need to be converted to strings.

    Returns:
        dict: Result indicating if a DNC prompt or related intent was detected.
    """
    # Extract the 'prompt' or the string representation from each Dnc object.
    dnc_prompts_str = [str(dnc.prompt) for dnc in dnc_prompts]  # Replace 'prompt' with the correct attribute
    prompt = f"""
    You are analyzing a call transcript to check if the user expressed any intention to be added to the "Do Not Call" (DNC) list.
    Below is a list of DNC-related prompts:
    {', '.join(dnc_prompts_str)}

    Analyze the following transcript and determine if the user's intent matches any of the above DNC prompts or if their intent is related to the DNC list.

    Provide your response in True or False only.

    Transcript:
    {transcript}
    """

    # Using the model to process the prompt
    model = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
    output_parser = StrOutputParser()

    # Assuming ChatPromptTemplate is being used to set the template
    prompt_template = ChatPromptTemplate.from_template(prompt)
    chain = prompt_template | model | output_parser

    # Get the result asynchronously
    result = await chain.ainvoke({"transcript": transcript})

    # Safely check the model output for True/False
    if result.strip().lower() == "true":
        return {"dnc_detected": True}
    elif result.strip().lower() == "false":
        return {"dnc_detected": False}
    else:
        return {"error": f"Unexpected model response: {result}"}

#/////////////////////////////////// Sync Inbound Calls from VAPI /////////////////////////////////////////
@router.post("/sync-inbound-calls")
async def sync_inbound_calls(
    user: Annotated[User, Depends(get_current_user)],
    background_tasks: BackgroundTasks
):
    """
    Manually sync inbound calls from VAPI that might have been missed by webhooks
    """
    try:
        # Get all call IDs from VAPI for this user's assistants
        user_assistants = await Assistant.filter(user=user).all()
        assistant_ids = [assistant.vapi_assistant_id for assistant in user_assistants]
        
        synced_count = 0
        
        for assistant_id in assistant_ids:
            url = f"https://api.vapi.ai/call"
            params = {"assistantId": assistant_id}
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=get_headers(), params=params)
            
            if response.status_code == 200:
                vapi_calls = response.json()
                
                for call in vapi_calls:
                    call_id = call.get("id")
                    
                    # Check if this call already exists in our database
                    existing_call = await CallLog.filter(call_id=call_id).first()
                    
                    if not existing_call:
                        # This is a new call (likely inbound)
                        customer_data = call.get("customer", {})
                        
                        # Extract customer information from call data
                        customer_data = call.get("customer", {})
                        assistant_overrides = call.get("assistantOverrides", {})
                        variable_values = assistant_overrides.get("variableValues", {})
                        
                        # Get customer name from variable values or default
                        first_name = variable_values.get("first_name", "")
                        last_name = variable_values.get("last_name", "")
                        customer_name = f"{first_name} {last_name}".strip() if first_name or last_name else "Inbound Call"
                        
                        # Get call start time
                        call_started_at = None
                        if call.get("createdAt"):
                            try:
                                call_started_at = datetime.fromisoformat(call.get("createdAt").replace("Z", "+00:00"))
                            except:
                                call_started_at = datetime.now()
                        
                        # Get call end time
                        call_ended_at = None
                        if call.get("endedAt"):
                            try:
                                call_ended_at = datetime.fromisoformat(call.get("endedAt").replace("Z", "+00:00"))
                            except:
                                call_ended_at = None
                        
                        new_call_log = await CallLog.create(
                            user=user,
                            call_id=call_id,
                            call_started_at=call_started_at,
                            call_ended_at=call_ended_at,
                            customer_number=customer_data.get("number"),
                            customer_name=customer_name,
                            status=call.get("status", "Unknown"),
                            call_ended_reason=call.get("endedReason", None),
                            cost=call.get("cost", 0),
                            call_duration=call.get("duration", 0),
                            is_transferred=False,
                            criteria_satisfied=False,
                            lead_id=None  # Inbound calls typically don't have lead_id
                        )
                        
                        # Add background task to get final call details (like in phone-call endpoint)
                        background_tasks.add_task(
                            get_call_details,
                            call_id=call_id, 
                            delay=300,  # 5 minutes delay
                            user_id=user.id
                        )
                        
                        synced_count += 1
        
        return {
            "success": True, 
            "detail": f"Successfully synced {synced_count} inbound calls"
        }
        
    except Exception as e:
        print(f"Error syncing inbound calls: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Sync error: {str(e)}")

#/////////////////////////////////// Number of inbound and outbound calls /////////////////////////////////////////
@router.get("/user/call-counts")
async def get_user_call_counts(user: Annotated[User, Depends(get_current_user)]):
    """
    Get count of inbound and outbound calls for the current user
    """
    try:
        # Getting all call logs for the current user
        call_logs = await CallLog.filter(user=user).all()
        
        inbound_count = 0
        outbound_count = 0
        today = date.today()
        
        # Count calls based on customer_name field
        for call_log in call_logs:
            if call_log.customer_name == "Inbound Call":
                inbound_count += 1
            else:
                outbound_count += 1
        
        # Count calls made today
        today_calls = 0
        for call_log in call_logs:
            if call_log.call_started_at and call_log.call_started_at.date() == today:
                today_calls += 1
        
        return {
            "inbound_calls": inbound_count,
            "outbound_calls": outbound_count,
            "total_calls": inbound_count + outbound_count,
            "today_calls": today_calls
        }
        
    except Exception as e:
        print(f"Error fetching call counts: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Internal server error: {str(e)}"
        )

#/////////////////////////////////// VAPI Webhook for Inbound Calls /////////////////////////////////////////
# @router.post("/vapi-webhook")
# async def vapi_webhook(request: Request):
#     """
#     Webhook endpoint to handle VAPI call events, especially inbound calls
#     """
#     try:
#         data = await request.json()
#         event_type = data.get("type")
        
#         if event_type == "call.created":
#             call_data = data.get("data", {})
#             call_id = call_data.get("id")
            
#             # Check if this call already exists in our database
#             existing_call = await CallLog.filter(call_id=call_id).first()
            
#             if not existing_call:
#                 # This is a new call (likely inbound)
#                 customer_data = call_data.get("customer", {})
#                 assistant_data = call_data.get("assistant", {})
                
#                 # Try to find the user based on assistant ID
#                 assistant = await Assistant.filter(vapi_assistant_id=call_data.get("assistantId")).first()
#                 user = assistant.user if assistant else None
                
#                 if user:
#                     await CallLog.create(
#                         user=user,
#                         call_id=call_id,
#                         call_started_at=datetime.fromisoformat(call_data.get("createdAt").replace("Z", "+00:00")) if call_data.get("createdAt") else None,
#                         customer_number=customer_data.get("number"),
#                         customer_name="Inbound Call",  # You might want to extract this from transcript later
#                         status=call_data.get("status", "Unknown"),
#                         # Add background task to get final details
#                     )
                    
#                     # Add background task to get call details after completion
#                     background_tasks.add_task(
#                         get_call_details, 
#                         call_id=call_id, 
#                         delay=300,  # 5 minutes delay
#                         user_id=user.id
#                     )
                    
#                     print(f"Inbound call logged: {call_id}")
        
#         return {"success": True, "detail": "Webhook processed successfully"}
        
#     except Exception as e:
#         print(f"Error processing webhook: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Webhook processing error: {str(e)}")

@router.get("/call-status/{call_id}")
async def get_call_processing_status(call_id: str, user: Annotated[User, Depends(get_current_user)]):
    """
    Check the processing status of a call, especially useful for long calls
    """
    try:
        call_detail_url = f"https://api.vapi.ai/call/{call_id}"
        async with httpx.AsyncClient() as client:
            response = await client.get(call_detail_url, headers=get_headers())
        
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to retrieve call details")

        call_data = response.json()
        
        # Get basic call info
        started_at = call_data.get("startedAt", None)
        ended_at = call_data.get("endedAt", None)
        status = call_data.get("status", "Unknown")
        
        # Calculate duration
        call_duration = None
        if started_at and ended_at:
            start_time = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            end_time = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
            call_duration = (end_time - start_time).total_seconds()
        
        # Check transcript status
        transcript = call_data.get("artifact", {}).get("transcript", "No transcript available")
        recording_url = call_data.get("artifact", {}).get("recordingUrl", "N/A")
        
        transcript_status = "not_available"
        if transcript and transcript != "No transcript available":
            word_count = len(transcript.split())
            sentence_count = len(transcript.split('.'))
            
            if call_duration and call_duration > 1800:  # > 30 minutes
                min_words = int(call_duration / 60 * 10)
                min_sentences = int(call_duration / 60 * 2)
            else:
                min_words = 50
                min_sentences = 10
            
            if word_count >= min_words and sentence_count >= min_sentences:
                transcript_status = "complete"
            else:
                transcript_status = "partial"
        
        # Check if call is still processing
        is_processing = status in ["in-progress", "queued", "connecting"]
        
        # Calculate processing progress for long calls
        processing_progress = None
        if call_duration and call_duration > 1800:  # Long call
            if transcript_status == "complete":
                processing_progress = 100
            elif transcript_status == "partial":
                processing_progress = 50
            elif transcript_status == "not_available":
                processing_progress = 25
        
        return {
            "call_id": call_id,
            "status": status,
            "is_processing": is_processing,
            "call_duration": call_duration,
            "call_duration_minutes": call_duration / 60 if call_duration else None,
            "transcript_status": transcript_status,
            "transcript_available": transcript != "No transcript available",
            "recording_available": recording_url != "N/A",
            "processing_progress": processing_progress,
            "started_at": started_at,
            "ended_at": ended_at,
            "cost": call_data.get("cost", 0),
            "ended_reason": call_data.get("endedReason", "Unknown")
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking call status: {str(e)}")

