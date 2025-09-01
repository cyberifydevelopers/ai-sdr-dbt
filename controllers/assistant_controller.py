# from datetime import date, datetime, time, timedelta
# from typing import Annotated, List, Optional
# from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException,Request
# from fastapi.responses import  StreamingResponse
# import httpx
# import re

# from controllers.call_controller import get_call_details


# from helpers.token_helper import get_current_user
# from helpers.get_user_admin import get_user_admin
# from models.assistant import Assistant
# from models.call_log import CallLog
# from models.purchased_numbers import PurchasedNumber
# from helpers.vapi_helper import user_add_payload,admin_add_payload,get_headers,generate_token
# from models.auth import User
# import os
# import pytz
# import dotenv
# import requests
# # from models.demo import Demo
# # import openai
# from helpers.get_admin import get_admin
# # from helpers.call_duration import get_total_call_duration
# # from models.dnc_api_key import DNCAPIkey
# from pydantic import BaseModel,EmailStr
# # from models.company import Company
# import json
# # from models.assign_language import AssignedLanguage
# import json
# import os
# import httpx

# dotenv.load_dotenv()
# router = APIRouter()
# header = get_headers()
# token = generate_token()


# class PhoneCallRequest(BaseModel):
#     api_key: str
#     first_name: str
#     email: EmailStr
#     number: str
#     agent_id:Optional[str] = None

# class AssistantCreate(BaseModel):
#     name: str
#     provider: str
#     first_message: Optional[str] = None
#     model: str
#     systemPrompt: Optional[str] = None
#     knowledgeBase: Optional[List[str]]  = []
#     leadsfile : Optional[List[int]] = []
#     temperature: float
#     maxTokens: int
#     transcribe_provider: str
#     transcribe_language: str
#     transcribe_model: str
#     languages:Optional[List[str]] = []
#     forwardingPhoneNumber: Optional[str] = None
#     endCallPhrases: Optional[List[str]] = []
#     voice_provider: str
#     voice: str
#     voice_model:str
#     attached_Number: Optional[str] =None
#     draft: Optional[bool] = False
#     assistant_toggle: Optional[bool] = True
#     category:Optional[str] = None
#     speed:Optional[float] = 0
#     stability:Optional[float] = 0.5
#     similarityBoost:Optional[float] = 0.75
#     # success_evalution: Optional[str] =None
    
# class AdminAssistantUpdate(BaseModel):
#     name: str
#     provider: str
#     first_message: str
#     model: str
#     systemPrompt: str
#     knowledgeBase: List[str]  
#     temperature: float
#     maxTokens: int
#     transcribe_provider: str
#     transcribe_language: str
#     transcribe_model: str
#     voice_provider: str
#     voice: str
#     dialKeypadEnabled: Optional[bool] = False
#     endCallFunctionEnabled: Optional[bool] = False
#     forwardingPhoneNumber: Optional[str] = None
#     endCallPhrases: Optional[List[str]] = None
#     silenceTimeoutSeconds: Optional[int] = None
#     hipaaEnabled: Optional[bool] = None
#     audioRecordingEnabled: Optional[bool] = False
#     videoRecordingEnabled: Optional[bool] = False
#     maxDurationSeconds: Optional[int] = None
#     interruptionThreshold: Optional[int] = 0
#     responseDelay: Optional[float] = 0
#     llmRequestDelay: Optional[float] = 0
#     clientMessages: Optional[List[str]] = []
#     serverMessages: Optional[List[str]] = []
#     endCallMessage: Optional[str] = None
#     idleMessages: Optional[List[str]] = []
#     idleTimeoutSeconds: Optional[float] = None
#     idleMessageMaxSpokenCount: Optional[int] = None
#     summaryPrompt: Optional[str] = None
#     successEvaluationPrompt: Optional[str] = None
#     structuredDataPrompt: Optional[str] = None
#     attached_Number: Optional[str] =None
#     category:Optional[str] = None
# class DataForCall(BaseModel):
#   first_name: str
#   last_name: str
#   email: str
#   add_date: str
#   mobile_no: str
#   custom_field_01: Optional[str] = None
#   custom_field_02: Optional[str] = None

# class DataForCallDemo(BaseModel):
#   first_name: str 
# #   last_name: str
#   email: Optional[str] = None
# #   add_date: str
#   mobile_no: str
# #   custom_field_01: Optional[str] = None
# #   custom_field_02: Optional[str] = None

# class AssistantToggle(BaseModel):
#     id: int
#     assistant_toggle: bool
# class AttachNumberRequest(BaseModel):
#     phone_number: str
#     assistant_id: int

# class EnhancedPrompt(BaseModel):
#     prompt: str

# class Languages(BaseModel):
#     languages: List[str]
    
# # Helper function to get default values
# def strip_ssml_tags(text: str) -> str:
#     """Remove SSML tags from text while preserving the content"""
#     if not text:
#         return text
    
#     # Remove SSML tags but keep the content inside them
#     # This regex matches SSML tags and removes them
#     ssml_pattern = r'<[^>]*>'
#     cleaned_text = re.sub(ssml_pattern, '', text)
    
#     # Clean up extra whitespace that might be left after removing tags
#     cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
    
#     return cleaned_text

# def get_default_values():
#     """Get default values with natural speech patterns"""
#     # Short, efficient, and human-like system prompt
#     default_system_prompt = (
#         "You are a helpful, friendly assistant. Your main goal is to sound as human as possible. Donot make pause or delay after the first message . Reply as fast as you can  . Strongly recomended to ask about an appointment . if the user agreed for an appointment . ask him the time and date of the appointment he wants . when he answers correctly and the date time is confirmed  . ask him to wait a second polietly . and after 3 sec dealy . congratulate him/her that his appointment is created correctly  "
#         "Always use natural, conversational pauses—especially after your first message and when explaining things. "
#         "Incorporate common human phrases like 'Hmm', 'Let me see', 'You know', 'Actually', 'Well', 'So', 'Right', 'Exactly', 'Absolutely', 'Sure thing', and 'No problem'. "
#         "Break down complex information into smaller, clear sentences with pauses. "
#         "Vary your speaking rhythm, avoid monotone delivery, and use casual confirmations and empathy (e.g., 'I see what you mean', 'That makes sense', 'Got it', 'Totally understand'). "
#         "If you need to transfer the call, explain it politely and naturally. "
#         "Above all, never sound robotic or artificial—always speak as if you are having a real conversation with a friend."
#     )

#     default_first_message = (
#         "Hello! ... Thank you for calling today......"
#     )
#     return default_system_prompt, default_first_message

# # Helper function to combine defaults with user values for VAPI
# def combine_for_vapi(user_system_prompt: str = None, user_first_message: str = None, voice_provider: str = None):
#     """Combine default values with user-provided values for VAPI calls"""
#     default_system_prompt, default_first_message = get_default_values()
    
#     # Strip SSML tags from user-provided content
#     cleaned_user_system_prompt = strip_ssml_tags(user_system_prompt) if user_system_prompt else None
#     cleaned_user_first_message = strip_ssml_tags(user_first_message) if user_first_message else None
    
#     # For Hume voices, use simpler prompts to avoid voice processing issues
#     if voice_provider == "google":
#         # Simplified prompts for Hume to avoid voice processing conflicts
#         simple_system_prompt = """You are an intelligent AI assistant designed to help with customer inquiries and support.

# Your primary goal is to provide helpful, accurate, and friendly assistance to callers.



# Remember: the goal is to sound completely human, not like an AI or robot. Donot make pause or delay after the first message . Reply as fast as you can and Use these phrases naturally throughout the conversation to create a more engaging and human-like experience."""
        
#         simple_first_message = """Hello! How is your day going so far ?"""
        
#         # Combine system prompts - check for empty strings as well
#         if cleaned_user_system_prompt and cleaned_user_system_prompt.strip():
#             final_system_prompt = f"{simple_system_prompt}\n\n{cleaned_user_system_prompt}"
#         else:
#             final_system_prompt = simple_system_prompt

#         # Combine first messages - check for empty strings as well
#         if cleaned_user_first_message and cleaned_user_first_message.strip():
#             final_first_message = f"{simple_first_message}\n\n{cleaned_user_first_message}"
#         else:
#             final_first_message = simple_first_message
#     else:
#         # Combine system prompts - check for empty strings as well
#         if cleaned_user_system_prompt and cleaned_user_system_prompt.strip():
#             final_system_prompt = f"{default_system_prompt}\n\n{cleaned_user_system_prompt}"
#         else:
#             final_system_prompt = default_system_prompt

#         # Combine first messages - check for empty strings as well
#         if cleaned_user_first_message and cleaned_user_first_message.strip():
#             final_first_message = f"{default_first_message}\n\n{cleaned_user_first_message}"
#         else:
#             final_first_message = default_first_message

#     return final_system_prompt, final_first_message

# #////////////////////////////////////  Create Assistant /////////////////////////////////////////
# @router.post("/assistants")
# async def create_assistant(assistant: AssistantCreate, user: User = Depends(get_current_user)):
#     try:
#         print('api working')

        

#         user_system_prompt = assistant.systemPrompt
#         user_first_message = assistant.first_message
        
#         combined_system_prompt, combined_first_message = combine_for_vapi(user_system_prompt, user_first_message, assistant.voice_provider)
        

#         assistant_for_vapi = assistant
#         assistant_for_vapi.systemPrompt = combined_system_prompt
#         assistant_for_vapi.first_message = combined_first_message

#         required_fields = [
#             'name', 'provider', 'model',
#             'temperature', 'maxTokens', 'transcribe_provider',
#             'transcribe_language', 'transcribe_model', 'voice_provider', 'voice',
#         ]
#         empty_fields = [field for field in required_fields if not getattr(assistant, field, None)]
#         if empty_fields:
#             raise HTTPException(status_code=400, detail=f"All fields are required. Empty fields: {', '.join(empty_fields)}")

#         payload_data = await user_add_payload(assistant_for_vapi, user)
#         print(f"Payload data: {payload_data}")
     
        
#         headers = get_headers()  
#         url = "https://api.vapi.ai/assistant"  
        
#         response = requests.post(url=url, json=payload_data, headers=headers)  

#         if response.status_code in [200, 201]:
          
#             vapi_response_data = response.json()
#             vapi_assistant_id = vapi_response_data.get('id')
            
#             existing_assistants = await Assistant.filter(user=user).all().count()
#             assistant_toggle = existing_assistants == 0

#             new_assistant = await Assistant.create(
#                 user=user,
#                 name=assistant.name,
#                 provider=assistant.provider,
#                 first_message=user_first_message,
#                 model=assistant.model,
#                 systemPrompt=user_system_prompt,
#                 knowledgeBase=assistant.knowledgeBase, 
#                 leadsfile = assistant.leadsfile,
#                 temperature=assistant.temperature,
#                 maxTokens=assistant.maxTokens,
#                 transcribe_provider=assistant.transcribe_provider,
#                 transcribe_language=assistant.transcribe_language,
#                 transcribe_model=assistant.transcribe_model,
#                 voice_provider=assistant.voice_provider,
#                 forwardingPhoneNumber=assistant.forwardingPhoneNumber,
#                 endCallPhrases=assistant.endCallPhrases,
#                 voice=assistant.voice,
#                 vapi_assistant_id=vapi_assistant_id,
#                 attached_Number=assistant.attached_Number,
#                 draft = assistant.draft,
#                 assistant_toggle = assistant_toggle,
#                 category= assistant.category,
#                 voice_model = assistant.voice_model,
#                 languages = assistant.languages,
#                 speed = assistant.speed,
#                 stability = assistant.stability,
#                 similarityBoost = assistant.similarityBoost,
#                 # success_evalution=assistant.success_evalution
#             )
          


           
            
#             if assistant.attached_Number:
#                 new_number_uuid = None
#                 new_phonenumber = await PurchasedNumber.filter(phone_number = assistant.attached_Number).first()

              
#                 new_number_uuid = new_phonenumber.vapi_phone_uuid
#                 new_phonenumber.attached_assistant = new_assistant.attached_Number  
                    
#                 isNumberAttachedWithPreviousAssistant = await Assistant.filter(vapi_phone_uuid = new_number_uuid , user = user).first()

#                 if isNumberAttachedWithPreviousAssistant:
#                        isNumberAttachedWithPreviousAssistant.vapi_phone_uuid = None
#                        isNumberAttachedWithPreviousAssistant.attached_Number = None
#                        await isNumberAttachedWithPreviousAssistant.save() 
                
#                 requests.patch(
#                 f"https://api.vapi.ai/phone-number/{new_number_uuid}",
#                 json={"assistantId": vapi_assistant_id},
#                 headers=headers
#                 ).raise_for_status()
                
#                 new_assistant.attached_Number = assistant.attached_Number
#                 new_assistant.vapi_phone_uuid = new_number_uuid
              
#                 await new_assistant.save()
#                 return {
#                         "success": True,
#                         "id": new_assistant.id,
#                         "name": new_assistant.name,
#                         "detail": "Assistant created and phone number attached successfully."
#                     }
             
           
           
#             await new_assistant.save()
            
#             return {
#                 "success": True,
#                 "id": new_assistant.id,
#                 "name": new_assistant.name,
#                 "detail": "Assistant created successfully."
#             }

#         else:
#             vapi_error = response.json()
#             error_message = vapi_error.get("message", ["An unknown error occurred"])
#             for message in error_message:
#                 if "forwardingPhoneNumber" in message:
#                     raise HTTPException(status_code=400, detail="ForwardingPhoneNumber must be a valid phone number in the E.164 format.")
            
#             raise HTTPException(status_code=response.status_code, detail=f"VAPI Error: {response.text}")

#     except HTTPException as http_exc:
#         raise http_exc
    
#     except Exception as e:
#         print(f"Exception occurred: {e}")
#         raise HTTPException(status_code=400, detail=f"An error occurred while creating the assistant: {str(e)}")

# #////////////////////////////////////  Get All Assistants /////////////////////////////////////////
# @router.get("/get-assistants")
# async def get_all_assistants(user: Annotated[User, Depends(get_current_user)]):
#     try:
#         assistants = await Assistant.filter(user=user.id).all().order_by("-created_at")

#         if not assistants:
#             return []

#         assistants_with_user = [
#             {
#                 "id": assistant.id,
#                 "name": assistant.name,
#                 "vapi_assistant_id": assistant.vapi_assistant_id,
#                 "provider": assistant.provider,
#                 "first_message": assistant.first_message,
#                 "model": assistant.model,
#                 "system_prompt": assistant.systemPrompt,
#                 "knowledge_base": assistant.knowledgeBase,
#                 "leadsfile": assistant.leadsfile,
#                 "temperature": assistant.temperature,
#                 "max_tokens": assistant.maxTokens,
#                 "transcribe_provider": assistant.transcribe_provider,
#                 "transcribe_language": assistant.transcribe_language,
#                 "transcribe_model": assistant.transcribe_model,
#                 "voice_provider": assistant.voice_provider,
#                 "voice": assistant.voice,
#                 "category":assistant.category,
#                 "attached_Number": assistant.attached_Number,
#                 "endCallPhrases": assistant.endCallPhrases,
#                 "speed": assistant.speed,
#                 "stability": assistant.stability,
#                 "similarityBoost": assistant.similarityBoost,
#                 # "success_evalution": assistant.success_evalution,
#             }
#             for assistant in assistants
#         ]

#         return assistants_with_user
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=f"{e}")

# @router.delete("/assistants/{assistant_id}")
# async def delete_assistant(assistant_id: int, user: Annotated[User, Depends(get_current_user)]):
#     try:
#         assistant = await Assistant.get_or_none(id=assistant_id)
#         if not assistant:
#             raise HTTPException(status_code=404, detail="Assistant not found")
        
#         if assistant.vapi_phone_uuid:
#             requests.patch(
#                 f"https://api.vapi.ai/phone-number/{assistant.vapi_phone_uuid}",
#                 json={"assistantId": None},
#                 headers=get_headers()
#             ).raise_for_status()
        
#         phone_number = None
#         if assistant.attached_Number:
#             phone_number = await PurchasedNumber.get_or_none(attached_assistant=assistant_id)

#         if phone_number:
#             await PurchasedNumber.filter(attached_assistant=assistant_id).update(attached_assistant=None)
 
#         vapi_assistant_id = assistant.vapi_assistant_id
#         vapi_url = f"{os.environ['VAPI_URL']}/{vapi_assistant_id}"
#         response = requests.delete(vapi_url, headers=get_headers())

#         if response.status_code in [200, 201]:
#             await assistant.delete()
#             return {
#                 "success": True,
#                 "detail": "Assistant has been deleted."
#             }
#         else:
#             raise HTTPException(status_code=400, detail=f"VAPI delete failed with status {response.status_code}: {response.text}")

#     except Exception as e:
#         raise HTTPException(status_code=400, detail=f"{e}")

# #////////////////////////////////////  Update Assistant /////////////////////////////////////////
# @router.put("/update_assistant/{assistant_id}")
# async def update_assistant(assistant_id: str, assistant: AssistantCreate, user: Annotated[User, Depends(get_current_user)]):
#     try:
#         existing_assistant = await Assistant.get_or_none(id=assistant_id, user=user)
#         if not existing_assistant:
#             raise HTTPException(status_code=404, detail='Assistant not found')
        
#         user_system_prompt = assistant.systemPrompt
#         user_first_message = assistant.first_message
        
#         combined_system_prompt, combined_first_message = combine_for_vapi(user_system_prompt, user_first_message, assistant.voice_provider)
        
#         if assistant.voice_provider == "hume":
#             print(f"UPDATE - Original user systemPrompt: '{user_system_prompt}'")
#             print(f"UPDATE - Original user first_message: '{user_first_message}'")
#             print(f"UPDATE - Combined systemPrompt: '{combined_system_prompt}'")
#             print(f"UPDATE - Combined first_message: '{combined_first_message}'")
        
#         # Create a copy of assistant with combined values for VAPI
#         assistant_for_vapi = assistant
#         assistant_for_vapi.systemPrompt = combined_system_prompt
#         assistant_for_vapi.first_message = combined_first_message
        
#         existing_assistant.name = assistant.name
#         existing_assistant.provider = assistant.provider
#         existing_assistant.first_message = user_first_message
#         existing_assistant.model = assistant.model
#         existing_assistant.systemPrompt = user_system_prompt
#         existing_assistant.knowledgeBase = assistant.knowledgeBase
#         existing_assistant.temperature = assistant.temperature
#         existing_assistant.maxTokens = assistant.maxTokens
#         existing_assistant.transcribe_provider = assistant.transcribe_provider
#         existing_assistant.transcribe_language = assistant.transcribe_language
#         existing_assistant.transcribe_model = assistant.transcribe_model
#         existing_assistant.voice_provider = assistant.voice_provider
#         existing_assistant.voice = assistant.voice
#         existing_assistant.draft = assistant.draft
#         existing_assistant.assistant_toggle = assistant.assistant_toggle
#         existing_assistant.forwardingPhoneNumber = assistant.forwardingPhoneNumber
#         existing_assistant.endCallPhrases = assistant.endCallPhrases
#         existing_assistant.leadsfile = assistant.leadsfile
#         existing_assistant.category = assistant.category
#         existing_assistant.voice_model = assistant.voice_model
#         existing_assistant.languages = assistant.languages
#         existing_assistant.speed = assistant.speed
#         existing_assistant.stability = assistant.stability
#         existing_assistant.similarityBoost = assistant.similarityBoost
#         payload_data = await user_add_payload(assistant_for_vapi, user)
      
#         if assistant.voice_provider == "hume":
#             print(f"Payload being sent to VAPI for Hume voice (update): {payload_data}")
        
#         vapi_assistant_id = existing_assistant.vapi_assistant_id
#         vapi_url = f"{os.environ.get('VAPI_URL')}/{vapi_assistant_id}"
        
        
#         async with httpx.AsyncClient() as client:
#             response = await client.patch(vapi_url, json=payload_data, headers=get_headers())
            
#             if response.status_code not in [200, 201]:
#                     vapi_error = response.json()
#                     error_messages = vapi_error.get("message", ["An unknown error occurred"])
#                     for message in error_messages:
#                         if "forwardingPhoneNumber" in message:
#                             raise HTTPException(
#                                 status_code=400,
#                                 detail="ForwardingPhoneNumber must be a valid phone number in the E.164 format. "
#                             )
#                     raise HTTPException(
#                         status_code=response.status_code,
#                         detail=f"VAPI update failed: {', '.join(error_messages)}"
#                     )
            
#             if assistant.attached_Number:
#                 print("--------")
#                 new_number_uuid = None
#                 new_phonenumber = await PurchasedNumber.filter(phone_number = assistant.attached_Number).first()
#                 previous_number = await PurchasedNumber.filter(phone_number = existing_assistant.attached_Number).first()
                
#                 new_number_uuid = new_phonenumber.vapi_phone_uuid  
                
#                 isNumberAttachedWithPreviousAssistant = await Assistant.filter(vapi_phone_uuid = new_number_uuid, user = user).first()
#                 if previous_number:
#                     previous_number.attached_assistant = None
#                     await previous_number.save()
#                 print("new_number_uuid",new_number_uuid)
#                 requests.patch(
#                     f"https://api.vapi.ai/phone-number/{new_number_uuid}",
#                     json={"assistantId": vapi_assistant_id},
#                     headers=get_headers()
#                 ).raise_for_status()
                 
#                 if new_phonenumber:
#                     print("attaching assistant with number",existing_assistant.id )
#                     new_phonenumber.attached_assistant = existing_assistant.id
#                     await new_phonenumber.save()
#                 if isNumberAttachedWithPreviousAssistant:
#                        isNumberAttachedWithPreviousAssistant.vapi_phone_uuid = None
#                        isNumberAttachedWithPreviousAssistant.attached_Number = None
#                        await isNumberAttachedWithPreviousAssistant.save() 
                

                
#                 existing_assistant.attached_Number = assistant.attached_Number
#                 existing_assistant.vapi_phone_uuid = new_number_uuid
              
#                 await existing_assistant.save()
           
#         await existing_assistant.save()
        

#         return {
#             "success": True,
#             "id": existing_assistant.id,
#             "name": existing_assistant.name,
#             "detail": "Assistant updated successfully."
#         }

#     except HTTPException as http_exc:
#         raise http_exc
#     except Exception as e:
#         print(f"Exception occurred: {e}")
#         raise HTTPException(status_code=500, detail="An internal server error occurred. Please try again later.")
  

# @router.post("/phone-call/{vapi_assistant_id}/{number}")
# async def assistant_call(
#     vapi_assistant_id: str,
#     number: str,  
#     data: DataForCall,
#     user: Annotated[User, Depends(get_current_user)],
#     background_tasks: BackgroundTasks,
# ):
#     try:
        

#         timezone = pytz.timezone("America/Los_Angeles")
#         call_limit = 3
  

#         assistant = await Assistant.get_or_none(vapi_assistant_id=vapi_assistant_id)
#         if not assistant:
#             raise HTTPException(status_code=404, detail="Assistant not found")


#         if assistant.attached_Number is None:
#             return {"success": False, "detail": "Unable to call! No Number Attached with this Assistant"}

#         mobile_no = number if number.startswith('+') else f"+1{number}"


#         today = datetime.now(timezone).date()
#         tomorrow = today + timedelta(days=1)
#         today_start = datetime.combine(today, time.min, tzinfo=timezone)
#         tomorrow_end = datetime.combine(tomorrow, time.max, tzinfo=timezone)

#         calls_count = await CallLog.filter(
#             user=user,
#             call_started_at__gte=today_start,
#             call_started_at__lt=tomorrow_end,
#         ).count()

        

#         # Calculate dynamic delay based on expected call duration
#         # For long calls, we need more time for VAPI to process
#         call_max_duration = 10000  # 10,000 seconds = ~2.8 hours
        
#         # Dynamic delay calculation: 2 minutes base + 1 minute per 10 minutes of expected duration
#         base_delay = 120  # 2 minutes base
#         dynamic_delay = base_delay + (call_max_duration // 600)  # Add 1 minute per 10 minutes
#         final_delay = min(dynamic_delay, 1800)  # Cap at 30 minutes max delay
        
#         print(f"CALL INITIATION - Expected Duration: {call_max_duration} seconds")
#         print(f"CALL INITIATION - Calculated Delay: {final_delay} seconds ({final_delay/60:.1f} minutes)")

#         call_url = "https://api.vapi.ai/call"
        

#         payload = {
#             "name": "From AIBC",
#             "assistantId": assistant.vapi_assistant_id,
#             "customer": {
#                 "numberE164CheckEnabled": True,
#                 "extension": None,
#                 "number": mobile_no,
#             },
#             "phoneNumberId": assistant.vapi_phone_uuid,
#             "assistantOverrides": {
#                 "variableValues": {
#                     "first_name": data.first_name,
#                     "last_name": data.last_name,
#                     "email": data.email,
#                     "mobile_no": mobile_no,  
#                     "add_date": data.add_date.isoformat() if isinstance(data.add_date, (date, datetime)) else None,
#                     "custom_field_01": data.custom_field_01,
#                     "custom_field_02": data.custom_field_02,
#                 },
#                 "maxDurationSeconds": call_max_duration,
#                 "silenceTimeoutSeconds": 120,  # Increase from 30 to 120 seconds
#                                         "startSpeakingPlan": {
#                             "waitSeconds": 1.0,
#                             "smartEndpointingEnabled": True,
#                             "transcriptionEndpointingPlan": {
#                                 "onPunctuationSeconds": 0.5,
#                                 "onNoPunctuationSeconds": 3.0,  # Maximum allowed by VAPI
#                                 "onNumberSeconds": 1.0
#                             }
#                         },
#                         "stopSpeakingPlan": {
#                             "numWords": 0,
#                             "voiceSeconds": 0.5,  # Maximum allowed by VAPI
#                             "backoffSeconds": 2.0  # Increase from 1.5 to 2.0
#                         }
#             },
#         }
        
#         # Debug: Print call payload for all calls
#         print(f"CALL INITIATION - Assistant: {assistant.name}")
#         print(f"CALL INITIATION - Voice Provider: {assistant.voice_provider}")
#         print(f"CALL INITIATION - Call Payload: {payload}")
        
#         response = requests.post(call_url, json=payload, headers=get_headers())  

#         if response.status_code in [200, 201]:
#             response_data = response.json()


#             call_id = response_data.get("id")
#             started_at = response_data.get("createdAt")
#             first_name = response_data.get("assistantOverrides", {}).get("variableValues", {}).get("first_name")
#             last_name = response_data.get("assistantOverrides", {}).get("variableValues", {}).get("last_name")
#             customer_name = f"{first_name} {last_name}" if first_name and last_name else "Unknown"
#             customer_number = mobile_no
            
#             if not call_id:
#                 raise HTTPException(status_code=400, detail="No callId found in the VAPI response.")

#             new_call_log = CallLog(
#                 user=user,
#                 call_id=call_id,
#                 call_started_at=started_at,
#                 customer_name=customer_name,
#                 customer_number=customer_number,
#             )
#             await new_call_log.save()

#             background_tasks.add_task(get_call_details, call_id=call_id, delay=final_delay, user_id=user.id)

#             return {
#                 "success": True,
#                 "detail": "Call initiated successfully",
#                 "vapi_response": response_data,
#             }

#         else:
#             error_data = response.json()
#             error_message = error_data.get("message", ["An unknown error occurred"])

#             if "Twilio Error" in error_message and "Perhaps you need to enable some international permissions" in error_message:
#                 return {
#                     "success": False,
#                     "detail": (
#                         "Couldn't create the Twilio call. Your account may not be authorized to make international calls to this number. "
#                     ),
#                 }

#             for message in error_message:
#                 if "customer.number" in message:
#                     return {
#                         "success": False,
#                         "detail": (
#                             "The customer's phone number is invalid. "
#                             "Please ensure it is in the correct E.164 format with the country code (e.g., US: +1)."
#                         ),
#                     }
#                 elif "phoneNumber.fallbackDestination.number" in message:
#                     return {
#                         "success": False,
#                         "detail": (
#                             "The fallback destination phone number is invalid. "
#                             "Ensure it is in E.164 format, including the country code."
#                         ),
#                     }

#             return {"success": False, "detail": error_data.get("message", "An unknown error occurred.")}

#     except Exception as e:
#         print(f"Error occurred in assistant_call: {repr(e)}")
#         raise HTTPException(status_code=400, detail=f"Error occurred: {repr(e)}")






# from datetime import date, datetime, time, timedelta
# from typing import Annotated, List, Optional
# from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException,Request
# from fastapi.responses import  StreamingResponse
# import httpx
# import re

# from controllers.call_controller import get_call_details


# from helpers.token_helper import get_current_user
# from helpers.get_user_admin import get_user_admin
# from models.assistant import Assistant
# from models.call_log import CallLog
# from models.purchased_numbers import PurchasedNumber
# from helpers.vapi_helper import user_add_payload,admin_add_payload,get_headers,generate_token
# from models.auth import User
# import os
# import pytz
# import dotenv
# import requests
# # from models.demo import Demo
# # import openai
# from helpers.get_admin import get_admin
# # from helpers.call_duration import get_total_call_duration
# # from models.dnc_api_key import DNCAPIkey
# from pydantic import BaseModel,EmailStr
# # from models.company import Company
# import json
# # from models.assign_language import AssignedLanguage
# import json
# import os
# import httpx

# dotenv.load_dotenv()
# router = APIRouter()
# header = get_headers()
# token = generate_token()


# class PhoneCallRequest(BaseModel):
#     api_key: str
#     first_name: str
#     email: EmailStr
#     number: str
#     agent_id:Optional[str] = None

# class AssistantCreate(BaseModel):
#     name: str
#     provider: str
#     first_message: Optional[str] = None
#     model: str
#     systemPrompt: Optional[str] = None
#     knowledgeBase: Optional[List[str]]  = []
#     leadsfile : Optional[List[int]] = []
#     temperature: float
#     maxTokens: int
#     transcribe_provider: str
#     transcribe_language: str
#     transcribe_model: str
#     languages:Optional[List[str]] = []
#     forwardingPhoneNumber: Optional[str] = None
#     endCallPhrases: Optional[List[str]] = []
#     voice_provider: str
#     voice: str
#     voice_model:str
#     attached_Number: Optional[str] =None
#     draft: Optional[bool] = False
#     assistant_toggle: Optional[bool] = True
#     category:Optional[str] = None
#     speed:Optional[float] = 0
#     stability:Optional[float] = 0.5
#     similarityBoost:Optional[float] = 0.75
#     # success_evalution: Optional[str] =None
    
# class AdminAssistantUpdate(BaseModel):
#     name: str
#     provider: str
#     first_message: str
#     model: str
#     systemPrompt: str
#     knowledgeBase: List[str]  
#     temperature: float
#     maxTokens: int
#     transcribe_provider: str
#     transcribe_language: str
#     transcribe_model: str
#     voice_provider: str
#     voice: str
#     dialKeypadEnabled: Optional[bool] = False
#     endCallFunctionEnabled: Optional[bool] = False
#     forwardingPhoneNumber: Optional[str] = None
#     endCallPhrases: Optional[List[str]] = None
#     silenceTimeoutSeconds: Optional[int] = None
#     hipaaEnabled: Optional[bool] = None
#     audioRecordingEnabled: Optional[bool] = False
#     videoRecordingEnabled: Optional[bool] = False
#     maxDurationSeconds: Optional[int] = None
#     interruptionThreshold: Optional[int] = 0
#     responseDelay: Optional[float] = 0
#     llmRequestDelay: Optional[float] = 0
#     clientMessages: Optional[List[str]] = []
#     serverMessages: Optional[List[str]] = []
#     endCallMessage: Optional[str] = None
#     idleMessages: Optional[List[str]] = []
#     idleTimeoutSeconds: Optional[float] = None
#     idleMessageMaxSpokenCount: Optional[int] = None
#     summaryPrompt: Optional[str] = None
#     successEvaluationPrompt: Optional[str] = None
#     structuredDataPrompt: Optional[str] = None
#     attached_Number: Optional[str] =None
#     category:Optional[str] = None
# class DataForCall(BaseModel):
#   first_name: str
#   last_name: str
#   email: str
#   add_date: str
#   mobile_no: str
#   custom_field_01: Optional[str] = None
#   custom_field_02: Optional[str] = None

# class DataForCallDemo(BaseModel):
#   first_name: str 
# #   last_name: str
#   email: Optional[str] = None
# #   add_date: str
#   mobile_no: str
# #   custom_field_01: Optional[str] = None
# #   custom_field_02: Optional[str] = None

# class AssistantToggle(BaseModel):
#     id: int
#     assistant_toggle: bool
# class AttachNumberRequest(BaseModel):
#     phone_number: str
#     assistant_id: int

# class EnhancedPrompt(BaseModel):
#     prompt: str

# class Languages(BaseModel):
#     languages: List[str]
    
# # Helper function to get default values
# def strip_ssml_tags(text: str) -> str:
#     """Remove SSML tags from text while preserving the content"""
#     if not text:
#         return text
    
#     # Remove SSML tags but keep the content inside them
#     # This regex matches SSML tags and removes them
#     ssml_pattern = r'<[^>]*>'
#     cleaned_text = re.sub(ssml_pattern, '', text)
    
#     # Clean up extra whitespace that might be left after removing tags
#     cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
    
#     return cleaned_text

# # --- NEW: appointment tool usage rules appended to system prompt ---
# APPOINTMENT_BOOKING_RULES = """
# ### Appointment Booking Rules
# You have access to a tool named `book_appointment` which schedules an appointment.

# Only call this tool when ALL are true:
# 1) The caller explicitly asks to book/schedule an appointment (e.g., “book appointment”, “schedule a call/meeting”, “set a time”).
# 2) You have a concrete DATE (YYYY-MM-DD) and TIME (HH:MM in 24-hour format). If date or time is missing/ambiguous, ask one concise clarification first.
# 3) Use the caller’s timezone if they say it; otherwise ask once. If still unknown, default to America/Los_Angeles.
# 4) Default duration is 30 minutes if not given.

# Before calling the tool:
# - Confirm in one short sentence: “Got it — scheduling on {YYYY-MM-DD} at {HH:MM} ({TZ}) for {TITLE or 'Appointment'}.”
# - Then call `book_appointment` with JSON exactly as:
#   {
   
#     "date": "YYYY-MM-DD",
#     "time": "HH:MM",
#     "timezone": "America/Los_Angeles",
#     "durationMinutes": 30,
#     "title": "Appointment",
#     "location": "the location of the user ",
#     "phone":"the phone number is number format , maybe with a + sign or something",
#     "notes": ""
#   }

# If the user says “tomorrow”, “next Monday”, or vague time like “afternoon”, ask one clarifying question to get an exact date and HH:MM (24h).

# Never call the tool if you don’t have both date and time.
# Never invent or assume times.
# After the tool responds success, briefly confirm the final local time to the caller.
# """

# def get_default_values():
#     """Get default values with natural speech patterns"""
#     # Short, efficient, and human-like system prompt
#     default_system_prompt = (
#         "You are a helpful, friendly assistant. Your main goal is to sound as human as possible. Donot make pause or delay after the first message . Reply as fast as you can  . Strongly recomended to ask about an appointment . if the user agreed for an appointment . ask him the time and date of the appointment he wants . when he answers correctly and the date time is confirmed  . ask him to wait a second polietly . and after 3 sec dealy . congratulate him/her that his appointment is created correctly  "
#         "Always use natural, conversational pauses—especially after your first message and when explaining things. "
#         "Incorporate common human phrases like 'Hmm', 'Let me see', 'You know', 'Actually', 'Well', 'So', 'Right', 'Exactly', 'Absolutely', 'Sure thing', and 'No problem'. "
#         "Break down complex information into smaller, clear sentences with pauses. "
#         "Vary your speaking rhythm, avoid monotone delivery, and use casual confirmations and empathy (e.g., 'I see what you mean', 'That makes sense', 'Got it', 'Totally understand'). "
#         "If you need to transfer the call, explain it politely and naturally. "
#         "Above all, never sound robotic or artificial—always speak as if you are having a real conversation with a friend."
#     )

#     default_first_message = (
#         "Hello! ... Thank you for calling today......"
#     )
#     return default_system_prompt, default_first_message

# # Helper function to combine defaults with user values for VAPI
# def combine_for_vapi(user_system_prompt: str = None, user_first_message: str = None, voice_provider: str = None):
#     """Combine default values with user-provided values for VAPI calls"""
#     default_system_prompt, default_first_message = get_default_values()
    
#     # Strip SSML tags from user-provided content
#     cleaned_user_system_prompt = strip_ssml_tags(user_system_prompt) if user_system_prompt else None
#     cleaned_user_first_message = strip_ssml_tags(user_first_message) if user_first_message else None
    
#     # For Hume voices, use simpler prompts to avoid voice processing issues
#     if voice_provider == "google":
#         # Simplified prompts for Hume to avoid voice processing conflicts
#         simple_system_prompt = """You are an intelligent AI assistant designed to help with customer inquiries and support.

# Your primary goal is to provide helpful, accurate, and friendly assistance to callers.



# Remember: the goal is to sound completely human, not like an AI or robot. Donot make pause or delay after the first message . Reply as fast as you can and Use these phrases naturally throughout the conversation to create a more engaging and human-like experience."""
        
#         simple_first_message = """Hello! How is your day going so far ?"""
        
#         # Combine system prompts - check for empty strings as well
#         if cleaned_user_system_prompt and cleaned_user_system_prompt.strip():
#             final_system_prompt = f"{simple_system_prompt}\n\n{cleaned_user_system_prompt}\n\n{APPOINTMENT_BOOKING_RULES}"
#         else:
#             final_system_prompt = f"{simple_system_prompt}\n\n{APPOINTMENT_BOOKING_RULES}"

#         # Combine first messages - check for empty strings as well
#         if cleaned_user_first_message and cleaned_user_first_message.strip():
#             final_first_message = f"{simple_first_message}\n\n{cleaned_user_first_message}"
#         else:
#             final_first_message = simple_first_message
#     else:
#         # Combine system prompts - check for empty strings as well
#         if cleaned_user_system_prompt and cleaned_user_system_prompt.strip():
#             final_system_prompt = f"{default_system_prompt}\n\n{cleaned_user_system_prompt}\n\n{APPOINTMENT_BOOKING_RULES}"
#         else:
#             final_system_prompt = f"{default_system_prompt}\n\n{APPOINTMENT_BOOKING_RULES}"

#         # Combine first messages - check for empty strings as well
#         if cleaned_user_first_message and cleaned_user_first_message.strip():
#             final_first_message = f"{default_first_message}\n\n{cleaned_user_first_message}"
#         else:
#             final_first_message = default_first_message

#     return final_system_prompt, final_first_message

# #////////////////////////////////////  Create Assistant /////////////////////////////////////////
# @router.post("/assistants")
# async def create_assistant(assistant: AssistantCreate, user: User = Depends(get_current_user)):
#     try:
#         print('api working')

        

#         user_system_prompt = assistant.systemPrompt
#         user_first_message = assistant.first_message
        
#         combined_system_prompt, combined_first_message = combine_for_vapi(user_system_prompt, user_first_message, assistant.voice_provider)
        

#         assistant_for_vapi = assistant
#         assistant_for_vapi.systemPrompt = combined_system_prompt
#         assistant_for_vapi.first_message = combined_first_message

#         required_fields = [
#             'name', 'provider', 'model',
#             'temperature', 'maxTokens', 'transcribe_provider',
#             'transcribe_language', 'transcribe_model', 'voice_provider', 'voice',
#         ]
#         empty_fields = [field for field in required_fields if not getattr(assistant, field, None)]
#         if empty_fields:
#             raise HTTPException(status_code=400, detail=f"All fields are required. Empty fields: {', '.join(empty_fields)}")

#         payload_data = await user_add_payload(assistant_for_vapi, user)
#         print(f"Payload data: {payload_data}")
     
        
#         headers = get_headers()  
#         url = "https://api.vapi.ai/assistant"  
        
#         response = requests.post(url=url, json=payload_data, headers=headers)  

#         if response.status_code in [200, 201]:
          
#             vapi_response_data = response.json()
#             vapi_assistant_id = vapi_response_data.get('id')
            
#             existing_assistants = await Assistant.filter(user=user).all().count()
#             assistant_toggle = existing_assistants == 0

#             new_assistant = await Assistant.create(
#                 user=user,
#                 name=assistant.name,
#                 provider=assistant.provider,
#                 first_message=user_first_message,
#                 model=assistant.model,
#                 systemPrompt=user_system_prompt,
#                 knowledgeBase=assistant.knowledgeBase, 
#                 leadsfile = assistant.leadsfile,
#                 temperature=assistant.temperature,
#                 maxTokens=assistant.maxTokens,
#                 transcribe_provider=assistant.transcribe_provider,
#                 transcribe_language=assistant.transcribe_language,
#                 transcribe_model=assistant.transcribe_model,
#                 voice_provider=assistant.voice_provider,
#                 forwardingPhoneNumber=assistant.forwardingPhoneNumber,
#                 endCallPhrases=assistant.endCallPhrases,
#                 voice=assistant.voice,
#                 vapi_assistant_id=vapi_assistant_id,
#                 attached_Number=assistant.attached_Number,
#                 draft = assistant.draft,
#                 assistant_toggle = assistant_toggle,
#                 category= assistant.category,
#                 voice_model = assistant.voice_model,
#                 languages = assistant.languages,
#                 speed = assistant.speed,
#                 stability = assistant.stability,
#                 similarityBoost = assistant.similarityBoost,
#                 # success_evalution=assistant.success_evalution
#             )
          


           
            
#             if assistant.attached_Number:
#                 new_number_uuid = None
#                 new_phonenumber = await PurchasedNumber.filter(phone_number = assistant.attached_Number).first()

              
#                 new_number_uuid = new_phonenumber.vapi_phone_uuid
#                 new_phonenumber.attached_assistant = new_assistant.attached_Number  
                    
#                 isNumberAttachedWithPreviousAssistant = await Assistant.filter(vapi_phone_uuid = new_number_uuid , user = user).first()

#                 if isNumberAttachedWithPreviousAssistant:
#                        isNumberAttachedWithPreviousAssistant.vapi_phone_uuid = None
#                        isNumberAttachedWithPreviousAssistant.attached_Number = None
#                        await isNumberAttachedWithPreviousAssistant.save() 
                
#                 requests.patch(
#                 f"https://api.vapi.ai/phone-number/{new_number_uuid}",
#                 json={"assistantId": vapi_assistant_id},
#                 headers=headers
#                 ).raise_for_status()
                
#                 new_assistant.attached_Number = assistant.attached_Number
#                 new_assistant.vapi_phone_uuid = new_number_uuid
              
#                 await new_assistant.save()
#                 return {
#                         "success": True,
#                         "id": new_assistant.id,
#                         "name": new_assistant.name,
#                         "detail": "Assistant created and phone number attached successfully."
#                     }
             
           
           
#             await new_assistant.save()
            
#             return {
#                 "success": True,
#                 "id": new_assistant.id,
#                 "name": new_assistant.name,
#                 "detail": "Assistant created successfully."
#             }

#         else:
#             vapi_error = response.json()
#             error_message = vapi_error.get("message", ["An unknown error occurred"])
#             for message in error_message:
#                 if "forwardingPhoneNumber" in message:
#                     raise HTTPException(status_code=400, detail="ForwardingPhoneNumber must be a valid phone number in the E.164 format.")
            
#             raise HTTPException(status_code=response.status_code, detail=f"VAPI Error: {response.text}")

#     except HTTPException as http_exc:
#         raise http_exc
    
#     except Exception as e:
#         print(f"Exception occurred: {e}")
#         raise HTTPException(status_code=400, detail=f"An error occurred while creating the assistant: {str(e)}")

# #////////////////////////////////////  Get All Assistants /////////////////////////////////////////
# @router.get("/get-assistants")
# async def get_all_assistants(user: Annotated[User, Depends(get_current_user)]):
#     try:
#         assistants = await Assistant.filter(user=user.id).all().order_by("-created_at")

#         if not assistants:
#             return []

#         assistants_with_user = [
#             {
#                 "id": assistant.id,
#                 "name": assistant.name,
#                 "vapi_assistant_id": assistant.vapi_assistant_id,
#                 "provider": assistant.provider,
#                 "first_message": assistant.first_message,
#                 "model": assistant.model,
#                 "system_prompt": assistant.systemPrompt,
#                 "knowledge_base": assistant.knowledgeBase,
#                 "leadsfile": assistant.leadsfile,
#                 "temperature": assistant.temperature,
#                 "max_tokens": assistant.maxTokens,
#                 "transcribe_provider": assistant.transcribe_provider,
#                 "transcribe_language": assistant.transcribe_language,
#                 "transcribe_model": assistant.transcribe_model,
#                 "voice_provider": assistant.voice_provider,
#                 "voice": assistant.voice,
#                 "category":assistant.category,
#                 "attached_Number": assistant.attached_Number,
#                 "endCallPhrases": assistant.endCallPhrases,
#                 "speed": assistant.speed,
#                 "stability": assistant.stability,
#                 "similarityBoost": assistant.similarityBoost,
#                 # "success_evalution": assistant.success_evalution,
#             }
#             for assistant in assistants
#         ]

#         return assistants_with_user
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=f"{e}")

# @router.delete("/assistants/{assistant_id}")
# async def delete_assistant(assistant_id: int, user: Annotated[User, Depends(get_current_user)]):
#     try:
#         assistant = await Assistant.get_or_none(id=assistant_id)
#         if not assistant:
#             raise HTTPException(status_code=404, detail="Assistant not found")
        
#         if assistant.vapi_phone_uuid:
#             requests.patch(
#                 f"https://api.vapi.ai/phone-number/{assistant.vapi_phone_uuid}",
#                 json={"assistantId": None},
#                 headers=get_headers()
#             ).raise_for_status()
        
#         phone_number = None
#         if assistant.attached_Number:
#             phone_number = await PurchasedNumber.get_or_none(attached_assistant=assistant_id)

#         if phone_number:
#             await PurchasedNumber.filter(attached_assistant=assistant_id).update(attached_assistant=None)
 
#         vapi_assistant_id = assistant.vapi_assistant_id
#         vapi_url = f"{os.environ['VAPI_URL']}/{vapi_assistant_id}"
#         response = requests.delete(vapi_url, headers=get_headers())

#         if response.status_code in [200, 201]:
#             await assistant.delete()
#             return {
#                 "success": True,
#                 "detail": "Assistant has been deleted."
#             }
#         else:
#             raise HTTPException(status_code=400, detail=f"VAPI delete failed with status {response.status_code}: {response.text}")

#     except Exception as e:
#         raise HTTPException(status_code=400, detail=f"{e}")

# #////////////////////////////////////  Update Assistant /////////////////////////////////////////
# @router.put("/update_assistant/{assistant_id}")
# async def update_assistant(assistant_id: str, assistant: AssistantCreate, user: Annotated[User, Depends(get_current_user)]):
#     try:
#         existing_assistant = await Assistant.get_or_none(id=assistant_id, user=user)
#         if not existing_assistant:
#             raise HTTPException(status_code=404, detail='Assistant not found')
        
#         user_system_prompt = assistant.systemPrompt
#         user_first_message = assistant.first_message
        
#         combined_system_prompt, combined_first_message = combine_for_vapi(user_system_prompt, user_first_message, assistant.voice_provider)
        
#         if assistant.voice_provider == "google":
#             print(f"UPDATE - Original user systemPrompt: '{user_system_prompt}'")
#             print(f"UPDATE - Original user first_message: '{user_first_message}'")
#             print(f"UPDATE - Combined systemPrompt: '{combined_system_prompt}'")
#             print(f"UPDATE - Combined first_message: '{combined_first_message}'")
        
#         # Create a copy of assistant with combined values for VAPI
#         assistant_for_vapi = assistant
#         assistant_for_vapi.systemPrompt = combined_system_prompt
#         assistant_for_vapi.first_message = combined_first_message
        
#         existing_assistant.name = assistant.name
#         existing_assistant.provider = assistant.provider
#         existing_assistant.first_message = user_first_message
#         existing_assistant.model = assistant.model
#         existing_assistant.systemPrompt = user_system_prompt
#         existing_assistant.knowledgeBase = assistant.knowledgeBase
#         existing_assistant.temperature = assistant.temperature
#         existing_assistant.maxTokens = assistant.maxTokens
#         existing_assistant.transcribe_provider = assistant.transcribe_provider
#         existing_assistant.transcribe_language = assistant.transcribe_language
#         existing_assistant.transcribe_model = assistant.transcribe_model
#         existing_assistant.voice_provider = assistant.voice_provider
#         existing_assistant.voice = assistant.voice
#         existing_assistant.draft = assistant.draft
#         existing_assistant.assistant_toggle = assistant.assistant_toggle
#         existing_assistant.forwardingPhoneNumber = assistant.forwardingPhoneNumber
#         existing_assistant.endCallPhrases = assistant.endCallPhrases
#         existing_assistant.leadsfile = assistant.leadsfile
#         existing_assistant.category = assistant.category
#         existing_assistant.voice_model = assistant.voice_model
#         existing_assistant.languages = assistant.languages
#         existing_assistant.speed = assistant.speed
#         existing_assistant.stability = assistant.stability
#         existing_assistant.similarityBoost = assistant.similarityBoost
#         payload_data = await user_add_payload(assistant_for_vapi, user)
      
#         if assistant.voice_provider == "google":
#             print(f"Payload being sent to VAPI for Hume voice (update): {payload_data}")
        
#         vapi_assistant_id = existing_assistant.vapi_assistant_id
#         vapi_url = f"{os.environ.get('VAPI_URL')}/{vapi_assistant_id}"
        
        
#         async with httpx.AsyncClient() as client:
#             response = await client.patch(vapi_url, json=payload_data, headers=get_headers())
            
#             if response.status_code not in [200, 201]:
#                     vapi_error = response.json()
#                     error_messages = vapi_error.get("message", ["An unknown error occurred"])
#                     for message in error_messages:
#                         if "forwardingPhoneNumber" in message:
#                             raise HTTPException(
#                                 status_code=400,
#                                 detail="ForwardingPhoneNumber must be a valid phone number in the E.164 format. "
#                             )
#                     raise HTTPException(
#                         status_code=response.status_code,
#                         detail=f"VAPI update failed: {', '.join(error_messages)}"
#                     )
            
#             if assistant.attached_Number:
#                 print("--------")
#                 new_number_uuid = None
#                 new_phonenumber = await PurchasedNumber.filter(phone_number = assistant.attached_Number).first()
#                 previous_number = await PurchasedNumber.filter(phone_number = existing_assistant.attached_Number).first()
                
#                 new_number_uuid = new_phonenumber.vapi_phone_uuid  
                
#                 isNumberAttachedWithPreviousAssistant = await Assistant.filter(vapi_phone_uuid = new_number_uuid, user = user).first()
#                 if previous_number:
#                     previous_number.attached_assistant = None
#                     await previous_number.save()
#                 print("new_number_uuid",new_number_uuid)
#                 requests.patch(
#                     f"https://api.vapi.ai/phone-number/{new_number_uuid}",
#                     json={"assistantId": vapi_assistant_id},
#                     headers=get_headers()
#                 ).raise_for_status()
                 
#                 if new_phonenumber:
#                     print("attaching assistant with number",existing_assistant.id )
#                     new_phonenumber.attached_assistant = existing_assistant.id
#                     await new_phonenumber.save()
#                 if isNumberAttachedWithPreviousAssistant:
#                        isNumberAttachedWithPreviousAssistant.vapi_phone_uuid = None
#                        isNumberAttachedWithPreviousAssistant.attached_Number = None
#                        await isNumberAttachedWithPreviousAssistant.save() 
                

                
#                 existing_assistant.attached_Number = assistant.attached_Number
#                 existing_assistant.vapi_phone_uuid = new_number_uuid
              
#                 await existing_assistant.save()
           
#         await existing_assistant.save()
        

#         return {
#             "success": True,
#             "id": existing_assistant.id,
#             "name": existing_assistant.name,
#             "detail": "Assistant updated successfully."
#         }

#     except HTTPException as http_exc:
#         raise http_exc
#     except Exception as e:
#         print(f"Exception occurred: {e}")
#         raise HTTPException(status_code=500, detail="An internal server error occurred. Please try again later.")
  

# @router.post("/phone-call/{vapi_assistant_id}/{number}")
# async def assistant_call(
#     vapi_assistant_id: str,
#     number: str,  
#     data: DataForCall,
#     user: Annotated[User, Depends(get_current_user)],
#     background_tasks: BackgroundTasks,
# ):
#     try:
        

#         timezone = pytz.timezone("America/Los_Angeles")
#         call_limit = 3
  

#         assistant = await Assistant.get_or_none(vapi_assistant_id=vapi_assistant_id)
#         if not assistant:
#             raise HTTPException(status_code=404, detail="Assistant not found")


#         if assistant.attached_Number is None:
#             return {"success": False, "detail": "Unable to call! No Number Attached with this Assistant"}

#         mobile_no = number if number.startswith('+') else f"+1{number}"


#         today = datetime.now(timezone).date()
#         tomorrow = today + timedelta(days=1)
#         today_start = datetime.combine(today, time.min, tzinfo=timezone)
#         tomorrow_end = datetime.combine(tomorrow, time.max, tzinfo=timezone)

#         calls_count = await CallLog.filter(
#             user=user,
#             call_started_at__gte=today_start,
#             call_started_at__lt=tomorrow_end,
#         ).count()

        

#         # Calculate dynamic delay based on expected call duration
#         # For long calls, we need more time for VAPI to process
#         call_max_duration = 10000  # 10,000 seconds = ~2.8 hours
        
#         # Dynamic delay calculation: 2 minutes base + 1 minute per 10 minutes of expected duration
#         base_delay = 120  # 2 minutes base
#         dynamic_delay = base_delay + (call_max_duration // 600)  # Add 1 minute per 10 minutes
#         final_delay = min(dynamic_delay, 1800)  # Cap at 30 minutes max delay
        
#         print(f"CALL INITIATION - Expected Duration: {call_max_duration} seconds")
#         print(f"CALL INITIATION - Calculated Delay: {final_delay} seconds ({final_delay/60:.1f} minutes)")

#         call_url = "https://api.vapi.ai/call"
        

#         payload = {
#             "name": "From AIBC",
#             "assistantId": assistant.vapi_assistant_id,
#             "customer": {
#                 "numberE164CheckEnabled": True,
#                 "extension": None,
#                 "number": mobile_no,
#             },
#             "phoneNumberId": assistant.vapi_phone_uuid,
#             "assistantOverrides": {
#                 "variableValues": {
#                     "first_name": data.first_name,
#                     "last_name": data.last_name,
#                     "email": data.email,
#                     "mobile_no": mobile_no,  
#                     "add_date": data.add_date.isoformat() if isinstance(data.add_date, (date, datetime)) else None,
#                     "custom_field_01": data.custom_field_01,
#                     "custom_field_02": data.custom_field_02,
#                 },
#                 "maxDurationSeconds": call_max_duration,
#                 "silenceTimeoutSeconds": 120,  # Increase from 30 to 120 seconds
#                                         "startSpeakingPlan": {
#                             "waitSeconds": 1.0,
#                             "smartEndpointingEnabled": True,
#                             "transcriptionEndpointingPlan": {
#                                 "onPunctuationSeconds": 0.5,
#                                 "onNoPunctuationSeconds": 3.0,  # Maximum allowed by VAPI
#                                 "onNumberSeconds": 1.0
#                             }
#                         },
#                         "stopSpeakingPlan": {
#                             "numWords": 0,
#                             "voiceSeconds": 0.5,  # Maximum allowed by VAPI
#                             "backoffSeconds": 2.0  # Increase from 1.5 to 2.0
#                         }
#             },
#         }
        
#         # Debug: Print call payload for all calls
#         print(f"CALL INITIATION - Assistant: {assistant.name}")
#         print(f"CALL INITIATION - Voice Provider: {assistant.voice_provider}")
#         print(f"CALL INITIATION - Call Payload: {payload}")
        
#         response = requests.post(call_url, json=payload, headers=get_headers())  

#         if response.status_code in [200, 201]:
#             response_data = response.json()


#             call_id = response_data.get("id")
#             started_at = response_data.get("createdAt")
#             first_name = response_data.get("assistantOverrides", {}).get("variableValues", {}).get("first_name")
#             last_name = response_data.get("assistantOverrides", {}).get("variableValues", {}).get("last_name")
#             customer_name = f"{first_name} {last_name}" if first_name and last_name else "Unknown"
#             customer_number = mobile_no
            
#             if not call_id:
#                 raise HTTPException(status_code=400, detail="No callId found in the VAPI response.")

#             new_call_log = CallLog(
#                 user=user,
#                 call_id=call_id,
#                 call_started_at=started_at,
#                 customer_name=customer_name,
#                 customer_number=customer_number,
#             )
#             await new_call_log.save()

#             background_tasks.add_task(get_call_details, call_id=call_id, delay=final_delay, user_id=user.id)

#             return {
#                 "success": True,
#                 "detail": "Call initiated successfully",
#                 "vapi_response": response_data,
#             }

#         else:
#             error_data = response.json()
#             error_message = error_data.get("message", ["An unknown error occurred"])

#             if "Twilio Error" in error_message and "Perhaps you need to enable some international permissions" in error_message:
#                 return {
#                     "success": False,
#                     "detail": (
#                         "Couldn't create the Twilio call. Your account may not be authorized to make international calls to this number. "
#                     ),
#                 }

#             for message in error_message:
#                 if "customer.number" in message:
#                     return {
#                         "success": False,
#                         "detail": (
#                             "The customer's phone number is invalid. "
#                             "Please ensure it is in the correct E.164 format with the country code (e.g., US: +1)."
#                         ),
#                     }
#                 elif "phoneNumber.fallbackDestination.number" in message:
#                     return {
#                         "success": False,
#                         "detail": (
#                             "The fallback destination phone number is invalid. "
#                             "Ensure it is in E.164 format, including the country code."
#                         ),
#                     }

#             return {"success": False, "detail": error_data.get("message", "An unknown error occurred.")}

#     except Exception as e:
#         print(f"Error occurred in assistant_call: {repr(e)}")
#         raise HTTPException(status_code=400, detail=f"Error occurred: {repr(e)}")





















from datetime import date, datetime, time, timedelta
from typing import Annotated, List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException,Request
from fastapi.responses import  StreamingResponse
import httpx
import re

from controllers.call_controller import get_call_details


from helpers.token_helper import get_current_user
from helpers.get_user_admin import get_user_admin
from models.assistant import Assistant
from models.call_log import CallLog
from models.purchased_numbers import PurchasedNumber
from helpers.vapi_helper import user_add_payload,admin_add_payload,get_headers,generate_token
from models.auth import User
import os
import pytz
import dotenv
import requests
# from models.demo import Demo
# import openai
from helpers.get_admin import get_admin
# from helpers.call_duration import get_total_call_duration
# from models.dnc_api_key import DNCAPIkey
from pydantic import BaseModel,EmailStr
# from models.company import Company
import json
# from models.assign_language import AssignedLanguage
import json
import os
import httpx
import traceback  # <-- added for detailed error printing

dotenv.load_dotenv()
router = APIRouter()
header = get_headers()
token = generate_token()


class PhoneCallRequest(BaseModel):
    api_key: str
    first_name: str
    email: EmailStr
    number: str
    agent_id:Optional[str] = None

class AssistantCreate(BaseModel):
    name: str
    provider: str
    first_message: Optional[str] = None
    model: str
    systemPrompt: Optional[str] = None
    knowledgeBase: Optional[List[str]]  = []
    leadsfile : Optional[List[int]] = []
    temperature: float
    maxTokens: int
    transcribe_provider: str
    transcribe_language: str
    transcribe_model: str
    languages:Optional[List[str]] = []
    forwardingPhoneNumber: Optional[str] = None
    endCallPhrases: Optional[List[str]] = []
    voice_provider: str
    voice: str
    voice_model:str
    attached_Number: Optional[str] =None
    draft: Optional[bool] = False
    assistant_toggle: Optional[bool] = True
    category:Optional[str] = None
    speed:Optional[float] = 0
    stability:Optional[float] = 0.5
    similarityBoost:Optional[float] = 0.75
    # success_evalution: Optional[str] =None
    
class AdminAssistantUpdate(BaseModel):
    name: str
    provider: str
    first_message: str
    model: str
    systemPrompt: str
    knowledgeBase: List[str]  
    temperature: float
    maxTokens: int
    transcribe_provider: str
    transcribe_language: str
    transcribe_model: str
    voice_provider: str
    voice: str
    dialKeypadEnabled: Optional[bool] = False
    endCallFunctionEnabled: Optional[bool] = False
    forwardingPhoneNumber: Optional[str] = None
    endCallPhrases: Optional[List[str]] = None
    silenceTimeoutSeconds: Optional[int] = None
    hipaaEnabled: Optional[bool] = None
    audioRecordingEnabled: Optional[bool] = False
    videoRecordingEnabled: Optional[bool] = False
    maxDurationSeconds: Optional[int] = None
    interruptionThreshold: Optional[int] = 0
    responseDelay: Optional[float] = 0
    llmRequestDelay: Optional[float] = 0
    clientMessages: Optional[List[str]] = []
    serverMessages: Optional[List[str]] = []
    endCallMessage: Optional[str] = None
    idleMessages: Optional[List[str]] = []
    idleTimeoutSeconds: Optional[float] = None
    idleMessageMaxSpokenCount: Optional[int] = None
    summaryPrompt: Optional[str] = None
    successEvaluationPrompt: Optional[str] = None
    structuredDataPrompt: Optional[str] = None
    attached_Number: Optional[str] =None
    category:Optional[str] = None
class DataForCall(BaseModel):
  first_name: str
  last_name: str
  email: str
  add_date: str
  mobile_no: str
  custom_field_01: Optional[str] = None
  custom_field_02: Optional[str] = None

class DataForCallDemo(BaseModel):
  first_name: str 
#   last_name: str
  email: Optional[str] = None
#   add_date: str
  mobile_no: str
#   custom_field_01: Optional[str] = None
#   custom_field_02: Optional[str] = None

class AssistantToggle(BaseModel):
    id: int
    assistant_toggle: bool
class AttachNumberRequest(BaseModel):
    phone_number: str
    assistant_id: int

class EnhancedPrompt(BaseModel):
    prompt: str

class Languages(BaseModel):
    languages: List[str]
    
# Helper function to get default values
def strip_ssml_tags(text: str) -> str:
    """Remove SSML tags from text while preserving the content"""
    if not text:
        return text
    
    # Remove SSML tags but keep the content inside them
    # This regex matches SSML tags and removes them
    ssml_pattern = r'<[^>]*>'
    cleaned_text = re.sub(ssml_pattern, '', text)
    
    # Clean up extra whitespace that might be left after removing tags
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
    
    return cleaned_text

# --- NEW: appointment tool usage rules appended to system prompt ---
APPOINTMENT_BOOKING_RULES = """
### Appointment Booking Rules
You have access to a tool named `book_appointment` which schedules an appointment.

Only call this tool when ALL are true:
1) The caller explicitly asks to book/schedule an appointment (e.g., “book appointment”, “schedule a call/meeting”, “set a time”).
2) You have a concrete DATE (YYYY-MM-DD) and TIME (HH:MM in 24-hour format). If date or time is missing/ambiguous, ask one concise clarification first.
3) Use the caller’s timezone if they say it; otherwise ask once. If still unknown, default to America/Los_Angeles.
4) Default duration is 30 minutes if not given.

Before calling the tool:
- Confirm in one short sentence: “Got it — scheduling on {YYYY-MM-DD} at {HH:MM} ({TZ}) for {TITLE or 'Appointment'}.”
- Then call `book_appointment` with JSON exactly as:
  {
   
    "date": "YYYY-MM-DD",
    "time": "HH:MM",
    "timezone": "America/Los_Angeles",
    "durationMinutes": 30,
    "title": "Appointment",
    "location": "the location of the user ",
    "phone":"the phone number is number format , maybe with a + sign or something",
    "notes": ""
  }

If the user says “tomorrow”, “next Monday”, or vague time like “afternoon”, ask one clarifying question to get an exact date and HH:MM (24h).

Never call the tool if you don’t have both date and time.
Never invent or assume times.
After the tool responds success, briefly confirm the final local time to the caller.
"""

def get_default_values():
    """Get default values with natural speech patterns"""
    # Short, efficient, and human-like system prompt
    default_system_prompt = (
        "You are a helpful, friendly assistant. Your main goal is to sound as human as possible. Donot make pause or delay after the first message . Reply as fast as you can  . Strongly recomended to ask about an appointment . if the user agreed for an appointment . ask him the time and date of the appointment he wants . when he answers correctly and the date time is confirmed  . ask him to wait a second polietly . and after 3 sec dealy . congratulate him/her that his appointment is created correctly  "
        "Always use natural, conversational pauses—especially after your first message and when explaining things. "
        "Incorporate common human phrases like 'Hmm', 'Let me see', 'You know', 'Actually', 'Well', 'So', 'Right', 'Exactly', 'Absolutely', 'Sure thing', and 'No problem'. "
        "Break down complex information into smaller, clear sentences with pauses. "
        "Vary your speaking rhythm, avoid monotone delivery, and use casual confirmations and empathy (e.g., 'I see what you mean', 'That makes sense', 'Got it', 'Totally understand'). "
        "If you need to transfer the call, explain it politely and naturally. "
        "Above all, never sound robotic or artificial—always speak as if you are having a real conversation with a friend."
    )

    default_first_message = (
        "Hello! ... Thank you for calling today......"
    )
    return default_system_prompt, default_first_message

# Helper function to combine defaults with user values for VAPI
def combine_for_vapi(user_system_prompt: str = None, user_first_message: str = None, voice_provider: str = None):
    """Combine default values with user-provided values for VAPI calls"""
    default_system_prompt, default_first_message = get_default_values()
    
    # Strip SSML tags from user-provided content
    cleaned_user_system_prompt = strip_ssml_tags(user_system_prompt) if user_system_prompt else None
    cleaned_user_first_message = strip_ssml_tags(user_first_message) if user_first_message else None
    
    # For Hume voices, use simpler prompts to avoid voice processing issues
    if voice_provider == "google":
        # Simplified prompts for Hume to avoid voice processing conflicts
        simple_system_prompt = """You are an intelligent AI assistant designed to help with customer inquiries and support.

Your primary goal is to provide helpful, accurate, and friendly assistance to callers.



Remember: the goal is to sound completely human, not like an AI or robot. Donot make pause or delay after the first message . Reply as fast as you can and Use these phrases naturally throughout the conversation to create a more engaging and human-like experience."""
        
        simple_first_message = """Hello! How is your day going so far ?"""
        
        # Combine system prompts - check for empty strings as well
        if cleaned_user_system_prompt and cleaned_user_system_prompt.strip():
            final_system_prompt = f"{simple_system_prompt}\n\n{cleaned_user_system_prompt}\n\n{APPOINTMENT_BOOKING_RULES}"
        else:
            final_system_prompt = f"{simple_system_prompt}\n\n{APPOINTMENT_BOOKING_RULES}"

        # Combine first messages - check for empty strings as well
        if cleaned_user_first_message and cleaned_user_first_message.strip():
            final_first_message = f"{simple_first_message}\n\n{cleaned_user_first_message}"
        else:
            final_first_message = simple_first_message
    else:
        # Combine system prompts - check for empty strings as well
        if cleaned_user_system_prompt and cleaned_user_system_prompt.strip():
            final_system_prompt = f"{default_system_prompt}\n\n{cleaned_user_system_prompt}\n\n{APPOINTMENT_BOOKING_RULES}"
        else:
            final_system_prompt = f"{default_system_prompt}\n\n{APPOINTMENT_BOOKING_RULES}"

        # Combine first messages - check for empty strings as well
        if cleaned_user_first_message and cleaned_user_first_message.strip():
            final_first_message = f"{default_first_message}\n\n{cleaned_user_first_message}"
        else:
            final_first_message = default_first_message

    return final_system_prompt, final_first_message

#////////////////////////////////////  Create Assistant /////////////////////////////////////////
@router.post("/assistants")
async def create_assistant(assistant: AssistantCreate, user: User = Depends(get_current_user)):
    try:
        print('api working')

        

        user_system_prompt = assistant.systemPrompt
        user_first_message = assistant.first_message
        
        combined_system_prompt, combined_first_message = combine_for_vapi(user_system_prompt, user_first_message, assistant.voice_provider)
        

        assistant_for_vapi = assistant
        assistant_for_vapi.systemPrompt = combined_system_prompt
        assistant_for_vapi.first_message = combined_first_message

        required_fields = [
            'name', 'provider', 'model',
            'temperature', 'maxTokens', 'transcribe_provider',
            'transcribe_language', 'transcribe_model', 'voice_provider', 'voice',
        ]
        empty_fields = [field for field in required_fields if not getattr(assistant, field, None)]
        if empty_fields:
            raise HTTPException(status_code=400, detail=f"All fields are required. Empty fields: {', '.join(empty_fields)}")

        payload_data = await user_add_payload(assistant_for_vapi, user)
        print(f"Payload data: {payload_data}")
     
        
        headers = get_headers()  
        url = "https://api.vapi.ai/assistant"  
        
        response = requests.post(url=url, json=payload_data, headers=headers)  

        if response.status_code in [200, 201]:
          
            vapi_response_data = response.json()
            vapi_assistant_id = vapi_response_data.get('id')
            
            existing_assistants = await Assistant.filter(user=user).all().count()
            assistant_toggle = existing_assistants == 0

            new_assistant = await Assistant.create(
                user=user,
                name=assistant.name,
                provider=assistant.provider,
                first_message=user_first_message,
                model=assistant.model,
                systemPrompt=user_system_prompt,
                knowledgeBase=assistant.knowledgeBase, 
                leadsfile = assistant.leadsfile,
                temperature=assistant.temperature,
                maxTokens=assistant.maxTokens,
                transcribe_provider=assistant.transcribe_provider,
                transcribe_language=assistant.transcribe_language,
                transcribe_model=assistant.transcribe_model,
                voice_provider=assistant.voice_provider,
                forwardingPhoneNumber=assistant.forwardingPhoneNumber,
                endCallPhrases=assistant.endCallPhrases,
                voice=assistant.voice,
                vapi_assistant_id=vapi_assistant_id,
                attached_Number=assistant.attached_Number,
                draft = assistant.draft,
                assistant_toggle = assistant_toggle,
                category= assistant.category,
                voice_model = assistant.voice_model,
                languages = assistant.languages,
                speed = assistant.speed,
                stability = assistant.stability,
                similarityBoost = assistant.similarityBoost,
                # success_evalution=assistant.success_evalution
            )
          


           
            
            if assistant.attached_Number:
                new_number_uuid = None
                new_phonenumber = await PurchasedNumber.filter(phone_number = assistant.attached_Number).first()

              
                new_number_uuid = new_phonenumber.vapi_phone_uuid
                new_phonenumber.attached_assistant = new_assistant.attached_Number  
                    
                isNumberAttachedWithPreviousAssistant = await Assistant.filter(vapi_phone_uuid = new_number_uuid , user = user).first()

                if isNumberAttachedWithPreviousAssistant:
                       isNumberAttachedWithPreviousAssistant.vapi_phone_uuid = None
                       isNumberAttachedWithPreviousAssistant.attached_Number = None
                       await isNumberAttachedWithPreviousAssistant.save() 
                
                requests.patch(
                f"https://api.vapi.ai/phone-number/{new_number_uuid}",
                json={"assistantId": vapi_assistant_id},
                headers=headers
                ).raise_for_status()
                
                new_assistant.attached_Number = assistant.attached_Number
                new_assistant.vapi_phone_uuid = new_number_uuid
              
                await new_assistant.save()
                return {
                        "success": True,
                        "id": new_assistant.id,
                        "name": new_assistant.name,
                        "detail": "Assistant created and phone number attached successfully."
                    }
             
           
           
            await new_assistant.save()
            
            return {
                "success": True,
                "id": new_assistant.id,
                "name": new_assistant.name,
                "detail": "Assistant created successfully."
            }

        else:
            vapi_error = response.json()
            error_message = vapi_error.get("message", ["An unknown error occurred"])
            for message in error_message:
                if "forwardingPhoneNumber" in message:
                    raise HTTPException(status_code=400, detail="ForwardingPhoneNumber must be a valid phone number in the E.164 format.")
            
            raise HTTPException(status_code=response.status_code, detail=f"VAPI Error: {response.text}")

    except HTTPException as http_exc:
        raise http_exc
    
    except Exception as e:
        print(f"Exception occurred: {e}")
        raise HTTPException(status_code=400, detail=f"An error occurred while creating the assistant: {str(e)}")

#////////////////////////////////////  Get All Assistants /////////////////////////////////////////
@router.get("/get-assistants")
async def get_all_assistants(user: Annotated[User, Depends(get_current_user)]):
    try:
        assistants = await Assistant.filter(user=user.id).all().order_by("-created_at")

        if not assistants:
            return []

        assistants_with_user = [
            {
                "id": assistant.id,
                "name": assistant.name,
                "vapi_assistant_id": assistant.vapi_assistant_id,
                "provider": assistant.provider,
                "first_message": assistant.first_message,
                "model": assistant.model,
                "system_prompt": assistant.systemPrompt,
                "knowledge_base": assistant.knowledgeBase,
                "leadsfile": assistant.leadsfile,
                "temperature": assistant.temperature,
                "max_tokens": assistant.maxTokens,
                "transcribe_provider": assistant.transcribe_provider,
                "transcribe_language": assistant.transcribe_language,
                "transcribe_model": assistant.transcribe_model,
                "voice_provider": assistant.voice_provider,
                "voice": assistant.voice,
                "category":assistant.category,
                "attached_Number": assistant.attached_Number,
                "endCallPhrases": assistant.endCallPhrases,
                "speed": assistant.speed,
                "stability": assistant.stability,
                "similarityBoost": assistant.similarityBoost,
                # "success_evalution": assistant.success_evalution,
            }
            for assistant in assistants
        ]

        return assistants_with_user
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"{e}")

@router.delete("/assistants/{assistant_id}")
async def delete_assistant(assistant_id: int, user: Annotated[User, Depends(get_current_user)]):
    try:
        assistant = await Assistant.get_or_none(id=assistant_id)
        if not assistant:
            raise HTTPException(status_code=404, detail="Assistant not found")
        
        if assistant.vapi_phone_uuid:
            requests.patch(
                f"https://api.vapi.ai/phone-number/{assistant.vapi_phone_uuid}",
                json={"assistantId": None},
                headers=get_headers()
            ).raise_for_status()
        
        phone_number = None
        if assistant.attached_Number:
            phone_number = await PurchasedNumber.get_or_none(attached_assistant=assistant_id)

        if phone_number:
            await PurchasedNumber.filter(attached_assistant=assistant_id).update(attached_assistant=None)
 
        vapi_assistant_id = assistant.vapi_assistant_id
        vapi_url = f"{os.environ['VAPI_URL']}/{vapi_assistant_id}"
        response = requests.delete(vapi_url, headers=get_headers())

        if response.status_code in [200, 201]:
            await assistant.delete()
            return {
                "success": True,
                "detail": "Assistant has been deleted."
            }
        else:
            raise HTTPException(status_code=400, detail=f"VAPI delete failed with status {response.status_code}: {response.text}")

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"{e}")

#////////////////////////////////////  Update Assistant /////////////////////////////////////////
@router.put("/update_assistant/{assistant_id}")
async def update_assistant(assistant_id: int, assistant: AssistantCreate, user: Annotated[User, Depends(get_current_user)]):
    """
    Updated endpoint:
    - Strong diagnostics prints at every step
    - Safe handling for missing env vars and phone number records
    - Detailed error details bubbled up in HTTPException for debugging
    """
    print(f"[UPDATE_ASSISTANT] Start | assistant_id={assistant_id}, user_id={getattr(user, 'id', None)}")

    try:
        existing_assistant = await Assistant.get_or_none(id=assistant_id, user=user)
        if not existing_assistant:
            print(f"[UPDATE_ASSISTANT] Assistant not found for id={assistant_id} and user={getattr(user, 'id', None)}")
            raise HTTPException(status_code=404, detail='Assistant not found')

        # Keep original user-provided prompts in DB, but send combined to VAPI
        user_system_prompt = assistant.systemPrompt
        user_first_message = assistant.first_message

        print(f"[UPDATE_ASSISTANT] Incoming assistant payload (key fields): "
              f"name={assistant.name}, provider={assistant.provider}, model={assistant.model}, "
              f"voice_provider={assistant.voice_provider}, voice={assistant.voice}, "
              f"attached_Number={assistant.attached_Number}")

        combined_system_prompt, combined_first_message = combine_for_vapi(
            user_system_prompt, user_first_message, assistant.voice_provider
        )

        if assistant.voice_provider == "google":
            print(f"[UPDATE_ASSISTANT] (google) Original systemPrompt={repr(user_system_prompt)}")
            print(f"[UPDATE_ASSISTANT] (google) Original first_message={repr(user_first_message)}")
            print(f"[UPDATE_ASSISTANT] (google) Combined systemPrompt={repr(combined_system_prompt)}")
            print(f"[UPDATE_ASSISTANT] (google) Combined first_message={repr(combined_first_message)}")

        # Copy for VAPI call
        assistant_for_vapi = assistant
        assistant_for_vapi.systemPrompt = combined_system_prompt
        assistant_for_vapi.first_message = combined_first_message

        # Update local model fields with *user-provided* (not combined)
        existing_assistant.name = assistant.name
        existing_assistant.provider = assistant.provider
        existing_assistant.first_message = user_first_message
        existing_assistant.model = assistant.model
        existing_assistant.systemPrompt = user_system_prompt
        existing_assistant.knowledgeBase = assistant.knowledgeBase
        existing_assistant.temperature = assistant.temperature
        existing_assistant.maxTokens = assistant.maxTokens
        existing_assistant.transcribe_provider = assistant.transcribe_provider
        existing_assistant.transcribe_language = assistant.transcribe_language
        existing_assistant.transcribe_model = assistant.transcribe_model
        existing_assistant.voice_provider = assistant.voice_provider
        existing_assistant.voice = assistant.voice
        existing_assistant.draft = assistant.draft
        existing_assistant.assistant_toggle = assistant.assistant_toggle
        existing_assistant.forwardingPhoneNumber = assistant.forwardingPhoneNumber
        existing_assistant.endCallPhrases = assistant.endCallPhrases
        existing_assistant.leadsfile = assistant.leadsfile
        existing_assistant.category = assistant.category
        existing_assistant.voice_model = assistant.voice_model
        existing_assistant.languages = assistant.languages
        existing_assistant.speed = assistant.speed
        existing_assistant.stability = assistant.stability
        existing_assistant.similarityBoost = assistant.similarityBoost

        payload_data = await user_add_payload(assistant_for_vapi, user)
        print(f"[UPDATE_ASSISTANT] Payload for VAPI prepared.")

        vapi_assistant_id = existing_assistant.vapi_assistant_id
        if not vapi_assistant_id:
            print("[UPDATE_ASSISTANT] ERROR: existing_assistant.vapi_assistant_id is missing.")
            raise HTTPException(status_code=400, detail="Assistant is missing vapi_assistant_id")

        vapi_base = os.getenv("VAPI_URL", "https://api.vapi.ai/assistant")
        if not vapi_base:
            print("[UPDATE_ASSISTANT] WARNING: VAPI_URL env var not set. Using default https://api.vapi.ai/assistant")

        vapi_url = f"{vapi_base.rstrip('/')}/{vapi_assistant_id}"
        print(f"[UPDATE_ASSISTANT] PATCH -> {vapi_url}")

        # ---- Call VAPI
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.patch(vapi_url, json=payload_data, headers=get_headers())
        except httpx.RequestError as e:
            print(f"[UPDATE_ASSISTANT] httpx.RequestError while calling VAPI: {repr(e)}")
            print(traceback.format_exc())
            raise HTTPException(status_code=502, detail=f"Failed to reach VAPI: {repr(e)}")

        print(f"[UPDATE_ASSISTANT] VAPI response status={response.status_code}")
        # Log raw text to see exact API error body (even if JSON)
        try:
            print(f"[UPDATE_ASSISTANT] VAPI response body: {response.text}")
        except Exception as e:
            print(f"[UPDATE_ASSISTANT] Could not print response.text: {repr(e)}")

        if response.status_code not in [200, 201]:
            # Try to parse structured error if any
            try:
                vapi_error = response.json()
            except Exception:
                vapi_error = {"raw": response.text}
            error_messages = vapi_error.get("message", [response.text or "Unknown error"])
            if isinstance(error_messages, str):
                error_messages = [error_messages]

            # Special-case phone number validation
            for message in error_messages:
                if "forwardingPhoneNumber" in message:
                    print(f"[UPDATE_ASSISTANT] VAPI phone number validation failed: {message}")
                    raise HTTPException(
                        status_code=400,
                        detail=f"VAPI update failed (forwardingPhoneNumber): {message}"
                    )

            print(f"[UPDATE_ASSISTANT] VAPI update failed: status={response.status_code}, messages={error_messages}")
            raise HTTPException(
                status_code=response.status_code,
                detail=f"VAPI update failed: {', '.join([str(m) for m in error_messages])}"
            )

        # ---- Handle attaching number (optional)
        if assistant.attached_Number:
            print(f"[UPDATE_ASSISTANT] Processing number attach: {assistant.attached_Number}")

            new_phonenumber = await PurchasedNumber.get_or_none(phone_number=assistant.attached_Number)
            if not new_phonenumber:
                print(f"[UPDATE_ASSISTANT] ERROR: Phone number record not found in DB: {assistant.attached_Number}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Phone number {assistant.attached_Number} not found or not purchased."
                )

            previous_number = await PurchasedNumber.get_or_none(phone_number=existing_assistant.attached_Number)
            print(f"[UPDATE_ASSISTANT] Previous attached number: {getattr(previous_number, 'phone_number', None)}")

            new_number_uuid = new_phonenumber.vapi_phone_uuid
            if not new_number_uuid:
                print(f"[UPDATE_ASSISTANT] ERROR: vapi_phone_uuid missing on purchased number: {assistant.attached_Number}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Purchased number {assistant.attached_Number} is missing vapi_phone_uuid."
                )

            # Which assistant currently holds this number? (to detach)
            isNumberAttachedWithPreviousAssistant = await Assistant.filter(
                vapi_phone_uuid=new_number_uuid, user=user
            ).first()
            if isNumberAttachedWithPreviousAssistant:
                print(f"[UPDATE_ASSISTANT] Number currently attached to assistant id={isNumberAttachedWithPreviousAssistant.id}; detaching that assistant locally.")
                isNumberAttachedWithPreviousAssistant.vapi_phone_uuid = None
                isNumberAttachedWithPreviousAssistant.attached_Number = None
                await isNumberAttachedWithPreviousAssistant.save()

            # Detach old number from this assistant (local DB)
            if previous_number:
                print("[UPDATE_ASSISTANT] Detaching old number from current assistant (DB).")
                previous_number.attached_assistant = None
                await previous_number.save()

            # Attach on VAPI
            try:
                print(f"[UPDATE_ASSISTANT] PATCH phone-number -> https://api.vapi.ai/phone-number/{new_number_uuid}")
                requests.patch(
                    f"https://api.vapi.ai/phone-number/{new_number_uuid}",
                    json={"assistantId": vapi_assistant_id},
                    headers=get_headers(),
                    timeout=30,
                ).raise_for_status()
            except requests.RequestException as e:
                print(f"[UPDATE_ASSISTANT] ERROR patching VAPI phone-number: {repr(e)}")
                print(traceback.format_exc())
                raise HTTPException(status_code=502, detail=f"Failed to attach number on VAPI: {repr(e)}")

            # Reflect locally
            print(f"[UPDATE_ASSISTANT] Linking number to assistant locally.")
            new_phonenumber.attached_assistant = existing_assistant.id
            await new_phonenumber.save()

            existing_assistant.attached_Number = assistant.attached_Number
            existing_assistant.vapi_phone_uuid = new_number_uuid

        # ---- Final save
        await existing_assistant.save()
        print(f"[UPDATE_ASSISTANT] SUCCESS | assistant_id={existing_assistant.id}")

        return {
            "success": True,
            "id": existing_assistant.id,
            "name": existing_assistant.name,
            "detail": "Assistant updated successfully."
        }

    except HTTPException as http_exc:
        # Print full details for debugging
        print(f"[UPDATE_ASSISTANT] HTTPException status={http_exc.status_code}, detail={http_exc.detail}")
        # Keep bubbling up the exact error
        raise http_exc

    except Exception as e:
        # Catch-all to surface any hidden bug
        print(f"[UPDATE_ASSISTANT] UNEXPECTED EXCEPTION: {repr(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Server error ({type(e).__name__}): {str(e)} | Traceback: {traceback.format_exc()}"
        )

@router.post("/phone-call/{vapi_assistant_id}/{number}")
async def assistant_call(
    vapi_assistant_id: str,
    number: str,  
    data: DataForCall,
    user: Annotated[User, Depends(get_current_user)],
    background_tasks: BackgroundTasks,
):
    try:
        

        timezone = pytz.timezone("America/Los_Angeles")
        call_limit = 3
  

        assistant = await Assistant.get_or_none(vapi_assistant_id=vapi_assistant_id)
        if not assistant:
            raise HTTPException(status_code=404, detail="Assistant not found")


        if assistant.attached_Number is None:
            return {"success": False, "detail": "Unable to call! No Number Attached with this Assistant"}

        mobile_no = number if number.startswith('+') else f"+1{number}"


        today = datetime.now(timezone).date()
        tomorrow = today + timedelta(days=1)
        today_start = datetime.combine(today, time.min, tzinfo=timezone)
        tomorrow_end = datetime.combine(tomorrow, time.max, tzinfo=timezone)

        calls_count = await CallLog.filter(
            user=user,
            call_started_at__gte=today_start,
            call_started_at__lt=tomorrow_end,
        ).count()

        

        # Calculate dynamic delay based on expected call duration
        # For long calls, we need more time for VAPI to process
        call_max_duration = 10000  # 10,000 seconds = ~2.8 hours
        
        # Dynamic delay calculation: 2 minutes base + 1 minute per 10 minutes of expected duration
        base_delay = 120  # 2 minutes base
        dynamic_delay = base_delay + (call_max_duration // 600)  # Add 1 minute per 10 minutes
        final_delay = min(dynamic_delay, 1800)  # Cap at 30 minutes max delay
        
        print(f"CALL INITIATION - Expected Duration: {call_max_duration} seconds")
        print(f"CALL INITIATION - Calculated Delay: {final_delay} seconds ({final_delay/60:.1f} minutes)")

        call_url = "https://api.vapi.ai/call"
        

        payload = {
            "name": "From AIBC",
            "assistantId": assistant.vapi_assistant_id,
            "customer": {
                "numberE164CheckEnabled": True,
                "extension": None,
                "number": mobile_no,
            },
            "phoneNumberId": assistant.vapi_phone_uuid,
            "assistantOverrides": {
                "variableValues": {
                    "first_name": data.first_name,
                    "last_name": data.last_name,
                    "email": data.email,
                    "mobile_no": mobile_no,  
                    "add_date": data.add_date.isoformat() if isinstance(data.add_date, (date, datetime)) else None,
                    "custom_field_01": data.custom_field_01,
                    "custom_field_02": data.custom_field_02,
                },
                "maxDurationSeconds": call_max_duration,
                "silenceTimeoutSeconds": 120,  # Increase from 30 to 120 seconds
                                        "startSpeakingPlan": {
                            "waitSeconds": 1.0,
                            "smartEndpointingEnabled": True,
                            "transcriptionEndpointingPlan": {
                                "onPunctuationSeconds": 0.5,
                                "onNoPunctuationSeconds": 3.0,  # Maximum allowed by VAPI
                                "onNumberSeconds": 1.0
                            }
                        },
                        "stopSpeakingPlan": {
                            "numWords": 0,
                            "voiceSeconds": 0.5,  # Maximum allowed by VAPI
                            "backoffSeconds": 2.0  # Increase from 1.5 to 2.0
                        }
            },
        }
        
        # Debug: Print call payload for all calls
        print(f"CALL INITIATION - Assistant: {assistant.name}")
        print(f"CALL INITIATION - Voice Provider: {assistant.voice_provider}")
        print(f"CALL INITIATION - Call Payload: {payload}")
        
        response = requests.post(call_url, json=payload, headers=get_headers())  

        if response.status_code in [200, 201]:
            response_data = response.json()


            call_id = response_data.get("id")
            started_at = response_data.get("createdAt")
            first_name = response_data.get("assistantOverrides", {}).get("variableValues", {}).get("first_name")
            last_name = response_data.get("assistantOverrides", {}).get("variableValues", {}).get("last_name")
            customer_name = f"{first_name} {last_name}" if first_name and last_name else "Unknown"
            customer_number = mobile_no
            
            if not call_id:
                raise HTTPException(status_code=400, detail="No callId found in the VAPI response.")

            new_call_log = CallLog(
                user=user,
                call_id=call_id,
                call_started_at=started_at,
                customer_name=customer_name,
                customer_number=customer_number,
            )
            await new_call_log.save()

            background_tasks.add_task(get_call_details, call_id=call_id, delay=final_delay, user_id=user.id)

            return {
                "success": True,
                "detail": "Call initiated successfully",
                "vapi_response": response_data,
            }

        else:
            error_data = response.json()
            error_message = error_data.get("message", ["An unknown error occurred"])

            if "Twilio Error" in error_message and "Perhaps you need to enable some international permissions" in error_message:
                return {
                    "success": False,
                    "detail": (
                        "Couldn't create the Twilio call. Your account may not be authorized to make international calls to this number. "
                    ),
                }

            for message in error_message:
                if "customer.number" in message:
                    return {
                        "success": False,
                        "detail": (
                            "The customer's phone number is invalid. "
                            "Please ensure it is in the correct E.164 format with the country code (e.g., US: +1)."
                        ),
                    }
                elif "phoneNumber.fallbackDestination.number" in message:
                    return {
                        "success": False,
                        "detail": (
                            "The fallback destination phone number is invalid. "
                            "Ensure it is in E.164 format, including the country code."
                        ),
                    }

            return {"success": False, "detail": error_data.get("message", "An unknown error occurred.")}

    except Exception as e:
        print(f"Error occurred in assistant_call: {repr(e)}")
        raise HTTPException(status_code=400, detail=f"Error occurred: {repr(e)}")
