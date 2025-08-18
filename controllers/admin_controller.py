# from fastapi import APIRouter, HTTPException, Depends
# from pydantic import BaseModel
# from models.auth import User
# from models.purchased_numbers import PurchasedNumber
# from models.assistant import Assistant
# from models.lead import Lead
# from models.call_log import CallLog
# from models.documents import Documents
# from helpers.token_helper import admin_required
# from helpers.vapi_helper import get_headers
# import os
# import httpx
# from dotenv import load_dotenv
# import requests

# load_dotenv()

# admin_router = APIRouter()

# #/////////////////////////////////////////// Users //////////////////////////////////////////////////////
# @admin_router.get("/users")
# async def get_all_users(current_user: User = Depends(admin_required)):
#     """
#     Fetch all users and their details along with total count.
#     Only accessible by admin users.
#     """
#     try:
#         # Fetch all users from the database
#         users = await User.all()
        
#         # Convert to response format
#         user_list = []
#         for user in users:
#             user_data = {
#                 "id": user.id,
#                 "name": user.name,
#                 "email": user.email,
#                 "email_verified": user.email_verified,
#                 "role": getattr(user, "role", "user"),
#                   # Default to "user" if role not set
#             }
#             user_list.append(user_data)
        
#         return {
#             "success": True,
#             "total_users": len(user_list),
#             "users": user_list,
#             "message": f"Successfully fetched {len(user_list)} users"
#         }
        
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Error fetching users: {str(e)}"
#         )

# #//////////////////////////////////// Update User ////////////////////////////////////////////////////
# class UserUpdateRequest(BaseModel):
#     name: str
#     email: str
#     role: str

# @admin_router.put("/users/{user_id}")
# async def update_user(user_id: int, user_data: UserUpdateRequest, current_user: User = Depends(admin_required)):
#     """
#     Update user's name and email.
#     Only accessible by admin users.
#     """
#     try:
#         name = user_data.name
#         email = user_data.email
#         role = user_data.role
        
#         # Validate role
#         valid_roles = ["user", "admin"]
#         if role not in valid_roles:
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}"
#             )
        
#         # Get the user to update
#         user = await User.get_or_none(id=user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")
        
#         # Check if email is already taken by another user
#         existing_user = await User.filter(email=email).exclude(id=user_id).first()
#         if existing_user:
#             raise HTTPException(
#                 status_code=400,
#                 detail="Email is already taken by another user"
#             )
        
#         # Update user data
#         user.name = name
#         user.email = email
#         user.role = role
#         await user.save()
        
#         return {
#             "success": True,
#             "detail": f"User with ID {user_id} has been updated successfully.",
#             "updated_user": {
#                 "id": user.id,
#                 "name": user.name,
#                 "email": user.email,
#                 "email_verified": user.email_verified,
#                 "role": user.role
#             }
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Error updating user: {str(e)}"
#         )
# #/////////////////////////////////////////// Delete User //////////////////////////////////////////////////////
# @admin_router.delete("/users/{user_id}")
# async def delete_user(user_id: int, current_user: User = Depends(admin_required)):
#     """
#     Delete a user and all their related data from the database.
#     Only accessible by admin users.
#     """
#     try:
#         user = await User.get_or_none(id=user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")
        
#         # Prevent admin from deleting themselves
#         if user.id == current_user.id:
#             raise HTTPException(status_code=400, detail="You cannot delete your own account")
        
#         # Get counts for reporting
#         assistants_count = await Assistant.filter(user=user).count()
#         call_logs_count = await CallLog.filter(user=user).count()
#         purchased_numbers_count = await PurchasedNumber.filter(user=user).count()
        
#         # Delete assistants (this will also clean up VAPI)
#         assistants = await Assistant.filter(user=user).all()
#         for assistant in assistants:
#             try:
#                 # Detach phone number from VAPI if attached
#                 if assistant.vapi_phone_uuid:
#                     requests.patch(
#                         f"https://api.vapi.ai/phone-number/{assistant.vapi_phone_uuid}",
#                         json={"assistantId": None},
#                         headers=get_headers()
#                     ).raise_for_status()
                
#                 # Delete assistant from VAPI
#                 vapi_assistant_id = assistant.vapi_assistant_id
#                 vapi_url = f"{os.environ.get('VAPI_URL', 'https://api.vapi.ai/assistant')}/{vapi_assistant_id}"
#                 requests.delete(vapi_url, headers=get_headers())
                
#             except Exception as e:
#                 print(f"Warning: Failed to delete assistant {assistant.id} from VAPI: {str(e)}")
            
#             # Delete assistant from local database
#             await assistant.delete()
        
#         # Delete call logs
#         await CallLog.filter(user=user).delete()
        
#         # Delete purchased numbers
#         await PurchasedNumber.filter(user=user).delete()
        
#         # Delete leads associated with user's files (simplified query)
#         try:
#             # First get all files associated with the user
#             from models.file import File
#             user_files = await File.filter(user=user).all()
#             file_ids = [file.id for file in user_files]
            
#             if file_ids:
#                 # Delete leads associated with these files
#                 await Lead.filter(file_id__in=file_ids).delete()
            
#             # Delete the files
#             await File.filter(user=user).delete()
            
#         except Exception as e:
#             print(f"Warning: Error deleting user files and associated leads: {str(e)}")
        
#         # Finally, delete the user
#         await user.delete()
        
#         return {
#             "success": True,
#             "detail": f"User with ID {user_id} and all related data have been deleted successfully.",
#             "deleted_data": {
#                 "assistants": assistants_count,
#                 "call_logs": call_logs_count,
#                 "purchased_numbers": purchased_numbers_count,
#                 "files_and_leads": "deleted"
#             }
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Error deleting user: {str(e)}"
#         )

# #/////////////////////////////////////////// Phone Numbers //////////////////////////////////////////////////////
# @admin_router.get("/phone-numbers")
# async def get_all_phone_numbers(current_user: User = Depends(admin_required)):
#     """
#     Fetch all purchased phone numbers and their details along with total count.
#     Only accessible by admin users.
#     """
#     try:
#         # Fetch all purchased numbers from the database
#         phone_numbers = await PurchasedNumber.all().prefetch_related('user')
        
#         # Convert to response format
#         phone_number_list = []
#         for phone_number in phone_numbers:
#             phone_data = {
#                 "id": phone_number.id,
#                 "phone_number": phone_number.phone_number,
#                 "friendly_name": phone_number.friendly_name,
#                 "region": phone_number.region,
#                 "postal_code": phone_number.postal_code,
#                 "iso_country": phone_number.iso_country,
#                 "last_month_payment": phone_number.last_month_payment,
#                 "created_at": phone_number.created_at,
#                 "updated_at": phone_number.updated_at,
#                 "attached_assistant": phone_number.attached_assistant,
#                 "vapi_phone_uuid": phone_number.vapi_phone_uuid,
#                 "user": {
#                     "id": phone_number.user.id,
#                     "name": phone_number.user.name,
#                     "email": phone_number.user.email
#                 } if phone_number.user else None
#             }
#             phone_number_list.append(phone_data)
        
#         return {
#             "success": True,
#             "total_phone_numbers": len(phone_number_list),
#             "phone_numbers": phone_number_list,
#             "message": f"Successfully fetched {len(phone_number_list)} phone numbers"
#         }
        
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Error fetching phone numbers: {str(e)}"
#         )

# #//////////////////////////////////// Delete Phone Number ////////////////////////////////////////////////////
# @admin_router.delete("/phone-numbers/{phone_number_id}")
# async def delete_phone_number(phone_number_id: int, current_user: User = Depends(admin_required)):
#     """
#     Delete a phone number from both local database and VAPI.
#     Only accessible by admin users.
#     """
#     try:
#         # Get the phone number from local database
#         phone_number = await PurchasedNumber.get_or_none(id=phone_number_id)
#         if not phone_number:
#             raise HTTPException(status_code=404, detail="Phone number not found")
        
#         vapi_phone_uuid = phone_number.vapi_phone_uuid
#         phone_number_value = phone_number.phone_number
        
#         # Check if phone number is attached to an assistant
#         if phone_number.attached_assistant:
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"Cannot delete phone number '{phone_number_value}' as it is currently attached to an assistant. Please detach it first."
#             )
        
#         # Delete from VAPI if vapi_phone_uuid exists
#         if vapi_phone_uuid:
#             try:
#                 # Get VAPI credentials from environment
#                 vapi_api_key = os.environ.get("VAPI_API_KEY")
#                 vapi_org_id = os.environ.get("VAPI_ORG_ID")
                
#                 if not vapi_api_key or not vapi_org_id:
#                     raise HTTPException(
#                         status_code=500,
#                         detail="VAPI credentials not configured"
#                     )
                
#                 # VAPI API endpoint for phone number deletion
#                 url = f"https://api.vapi.ai/phone-number/{vapi_phone_uuid}"
#                 headers = {
#                     "Authorization": f"Bearer {vapi_api_key}",
#                     "Content-Type": "application/json"
#                 }
                
#                 # Make delete request to VAPI
#                 async with httpx.AsyncClient() as client:
#                     response = await client.delete(url, headers=headers)
                    
#                     if response.status_code in [200, 201, 204]:
#                         print(f"Successfully deleted phone number {vapi_phone_uuid} from VAPI")
#                     else:
#                         print(f"Warning: Failed to delete phone number {vapi_phone_uuid} from VAPI. Status: {response.status_code}")
                        
#             except Exception as e:
#                 print(f"Warning: Error deleting phone number {vapi_phone_uuid} from VAPI: {str(e)}")
#                 # Continue with local deletion even if VAPI deletion fails
        
#         # Delete from local database
#         await phone_number.delete()
        
#         return {
#             "success": True,
#             "detail": f"Phone number '{phone_number_value}' has been deleted successfully.",
#             "deleted_data": {
#                 "phone_number_id": phone_number_id,
#                 "phone_number": phone_number_value,
#                 "vapi_phone_uuid": vapi_phone_uuid,
#                 "vapi_deleted": vapi_phone_uuid is not None
#             }
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Error deleting phone number: {str(e)}"
#         )

# #/////////////////////////////////////////// Assistant ///////////////////////////////////////////////
# @admin_router.get("/assistants")
# async def get_all_assistants(current_user: User = Depends(admin_required)):
#     """
#     Fetch all assistants and their details along with total count.
#     Only accessible by admin users.
#     """
#     try:
#         # Fetch all assistants from the database
#         assistants = await Assistant.all().prefetch_related('user')
        
#         # Convert to response format
#         assistant_list = []
#         for assistant in assistants:
#             assistant_data = {
#                 "id": assistant.id,
#                 "vapi_assistant_id": assistant.vapi_assistant_id,
#                 "name": assistant.name,
#                 "provider": assistant.provider,
#                 "first_message": assistant.first_message,
#                 "model": assistant.model,
#                 "systemPrompt": assistant.systemPrompt,
#                 "knowledgeBase": assistant.knowledgeBase,
#                 "leadsfile": assistant.leadsfile,
#                 "temperature": assistant.temperature,
#                 "maxTokens": assistant.maxTokens,
#                 "transcribe_provider": assistant.transcribe_provider,
#                 "transcribe_language": assistant.transcribe_language,
#                 "transcribe_model": assistant.transcribe_model,
#                 "voice_provider": assistant.voice_provider,
#                 "voice": assistant.voice,
#                 "forwardingPhoneNumber": assistant.forwardingPhoneNumber,
#                 "endCallPhrases": assistant.endCallPhrases,
#                 "attached_Number": assistant.attached_Number,
#                 "vapi_phone_uuid": assistant.vapi_phone_uuid,
#                 "draft": assistant.draft,
#                 "assistant_toggle": assistant.assistant_toggle,
#                 "success_evalution": assistant.success_evalution,
#                 "category": assistant.category,
#                 "voice_model": assistant.voice_model,
#                 "languages": assistant.languages,
#                 "created_at": assistant.created_at,
#                 "updated_at": assistant.updated_at,
#                 "speed": assistant.speed,
#                 "stability": assistant.stability,
#                 "similarityBoost": assistant.similarityBoost,
#                 "user": {
#                     "id": assistant.user.id,
#                     "name": assistant.user.name,
#                     "email": assistant.user.email
#                 } if assistant.user else None
#             }
#             assistant_list.append(assistant_data)
        
#         return {
#             "success": True,
#             "total_assistants": len(assistant_list),
#             "assistants": assistant_list,
#             "message": f"Successfully fetched {len(assistant_list)} assistants"
#         }
        
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Error fetching assistants: {str(e)}"
#         )
# #/////////////////////////////////////////// Delete Assistant //////////////////////////////////////////////////////
# @admin_router.delete("/assistants/{assistant_id}")
# async def delete_assistant(assistant_id: int, current_user: User = Depends(admin_required)):
#     """
#     Delete an assistant from both VAPI and local database.
#     Only accessible by admin users.
#     """
#     try:
#         assistant = await Assistant.get_or_none(id=assistant_id)
#         if not assistant:
#             raise HTTPException(status_code=404, detail="Assistant not found")
        
#         # Detach phone number from VAPI if attached
#         if assistant.vapi_phone_uuid:
#             try:
#                 requests.patch(
#                     f"https://api.vapi.ai/phone-number/{assistant.vapi_phone_uuid}",
#                     json={"assistantId": None},
#                     headers=get_headers()
#                 ).raise_for_status()
#             except Exception as e:
#                 print(f"Warning: Failed to detach phone number from VAPI: {str(e)}")
        
#         # Clean up phone number in local database
#         if assistant.attached_Number:
#             phone_number = await PurchasedNumber.get_or_none(attached_assistant=assistant_id)
#             if phone_number:
#                 await PurchasedNumber.filter(attached_assistant=assistant_id).update(attached_assistant=None)
 
#         # Delete assistant from VAPI
#         vapi_assistant_id = assistant.vapi_assistant_id
#         vapi_url = f"{os.environ.get('VAPI_URL', 'https://api.vapi.ai/assistant')}/{vapi_assistant_id}"
        
#         try:
#             response = requests.delete(vapi_url, headers=get_headers())
            
#             if response.status_code in [200, 201, 204]:
#                 # Delete from local database
#                 await assistant.delete()
#                 return {
#                     "success": True,
#                     "detail": "Assistant has been deleted successfully from both VAPI and local database."
#                 }
#             else:
#                 # If VAPI deletion fails, still delete from local database but warn
#                 await assistant.delete()
#                 return {
#                     "success": True,
#                     "detail": f"Assistant deleted from local database. VAPI deletion failed with status {response.status_code}: {response.text}"
#                 }
                
#         except Exception as e:
#             # If VAPI request fails completely, still delete from local database
#             await assistant.delete()
#             return {
#                 "success": True,
#                 "detail": f"Assistant deleted from local database. VAPI deletion failed: {str(e)}"
#             }

#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Error deleting assistant: {str(e)}"
#         )

# #/////////////////////////////////////////// Leads ////////////////////////////////////////////////
# @admin_router.get("/leadss")
# async def get_all_leads(current_user: User = Depends(admin_required)):
#     """
#     Fetch all leads and their details along with total count.
#     Only accessible by admin users.
#     """
#     try:
#         # Fetch all leads from the database
#         leads = await Lead.all()
        
#         # Convert to response format
#         lead_list = []
#         for lead in leads:
#             lead_data = {
#                 "id": lead.id,
#                 "first_name": lead.first_name,
#                 "last_name": lead.last_name,
#                 "email": lead.email,
#                 "add_date": lead.add_date,
#                 "salesforce_id": lead.salesforce_id,
#                 "mobile": lead.mobile,
#                 "state": lead.state,
#                 "timezone": lead.timezone,
#                 "dnc": lead.dnc,
#                 "submit_for_approval": lead.submit_for_approval,
#                 "other_data": lead.other_data,
#                 "last_called_at": lead.last_called_at,
#                 "call_count": lead.call_count,
#                 "created_at": lead.created_at,
#                 "updated_at": lead.updated_at
#             }
#             lead_list.append(lead_data)
        
#         return {
#             "success": True,
#             "total_leads": len(lead_list),
#             "leads": lead_list,
#             "message": f"Successfully fetched {len(lead_list)} leads"
#         }
        
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Error fetching leads: {str(e)}"
#         )
# #/////////////////////////////////////////// Update Lead Log //////////////////////////////////////////////////////
# class LeadUpdateRequest(BaseModel):
#     first_name: str
#     last_name: str
#     email: str
#     add_date: str  # Will be converted to date
#     salesforce_id: str = None
#     mobile: str
#     state: str = None
#     timezone: str = None
#     dnc: bool = False
#     submit_for_approval: bool = False
#     other_data: dict = None
#     call_count: int = 0

# @admin_router.put("/leads/{lead_id}")
# async def update_lead(lead_id: int, lead_data: LeadUpdateRequest, current_user: User = Depends(admin_required)):
#     """
#     Update lead fields.
#     Only accessible by admin users.
#     """
#     try:
#         from datetime import datetime
        
#         # Get the lead to update
#         lead = await Lead.get_or_none(id=lead_id)
#         if not lead:
#             raise HTTPException(status_code=404, detail="Lead not found")
        
#         # Convert add_date string to date object
#         try:
#             add_date = datetime.strptime(lead_data.add_date, "%Y-%m-%d").date()
#         except ValueError:
#             raise HTTPException(
#                 status_code=400,
#                 detail="Invalid date format. Use YYYY-MM-DD format"
#             )
        
#         # Update lead fields
#         lead.first_name = lead_data.first_name
#         lead.last_name = lead_data.last_name
#         lead.email = lead_data.email
#         lead.add_date = add_date
#         lead.salesforce_id = lead_data.salesforce_id
#         lead.mobile = lead_data.mobile
#         lead.state = lead_data.state
#         lead.timezone = lead_data.timezone
#         lead.dnc = lead_data.dnc
#         lead.submit_for_approval = lead_data.submit_for_approval
#         lead.other_data = lead_data.other_data
#         lead.call_count = lead_data.call_count
        
#         await lead.save()
        
#         return {
#             "success": True,
#             "detail": f"Lead with ID {lead_id} has been updated successfully.",
#             "updated_lead": {
#                 "id": lead.id,
#                 "first_name": lead.first_name,
#                 "last_name": lead.last_name,
#                 "email": lead.email,
#                 "add_date": lead.add_date.isoformat(),
#                 "salesforce_id": lead.salesforce_id,
#                 "mobile": lead.mobile,
#                 "state": lead.state,
#                 "timezone": lead.timezone,
#                 "dnc": lead.dnc,
#                 "submit_for_approval": lead.submit_for_approval,
#                 "other_data": lead.other_data,
#                 "last_called_at": lead.last_called_at.isoformat() if lead.last_called_at else None,
#                 "call_count": lead.call_count,
#                 "created_at": lead.created_at.isoformat(),
#                 "updated_at": lead.updated_at.isoformat()
#             }
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Error updating lead: {str(e)}"
#         )

# #/////////////////////////////////////////// Call logs //////////////////////////////////////////////////////
# @admin_router.get("/call-logs")
# async def get_all_call_logs(current_user: User = Depends(admin_required)):
#     """
#     Fetch all call logs and their details along with total count.
#     Only accessible by admin users.
#     """
#     try:
#         # Fetch all call logs from the database
#         call_logs = await CallLog.all().prefetch_related('user')
        
#         # Convert to response format
#         call_log_list = []
#         for call_log in call_logs:
#             call_log_data = {
#                 "id": call_log.id,
#                 "lead_id": call_log.lead_id,
#                 "call_started_at": call_log.call_started_at,
#                 "customer_number": call_log.customer_number,
#                 "customer_name": call_log.customer_name,
#                 "call_id": call_log.call_id,
#                 "cost": call_log.cost,
#                 "call_ended_at": call_log.call_ended_at,
#                 "call_ended_reason": call_log.call_ended_reason,
#                 "call_duration": call_log.call_duration,
#                 "is_transferred": call_log.is_transferred,
#                 "status": call_log.status,
#                 "criteria_satisfied": call_log.criteria_satisfied,
#                 "user": {
#                     "id": call_log.user.id,
#                     "name": call_log.user.name,
#                     "email": call_log.user.email
#                 } if call_log.user else None
#             }
#             call_log_list.append(call_log_data)
        
#         return {
#             "success": True,
#             "total_call_logs": len(call_log_list),
#             "call_logs": call_log_list,
#             "message": f"Successfully fetched {len(call_log_list)} call logs"
#         }
        
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Error fetching call logs: {str(e)}"
#         )

# #/////////////////////////////////////////// call logs from vapi //////////////////////////////////////////////////////
# @admin_router.get("/vapi-call-logs")
# async def get_vapi_call_logs(current_user: User = Depends(admin_required)):
#     """
#     Fetch all call logs from VAPI and their details along with total count.
#     Only accessible by admin users.
#     """
#     try:
#         # Get VAPI credentials from environment
#         vapi_api_key = os.environ.get("VAPI_API_KEY")
#         vapi_org_id = os.environ.get("VAPI_ORG_ID")
        
#         if not vapi_api_key or not vapi_org_id:
#             raise HTTPException(
#                 status_code=500,
#                 detail="VAPI credentials not configured"
#             )
        
#         # VAPI API endpoint for call logs
#         url = "https://api.vapi.ai/call/"
#         headers = {
#             "Authorization": f"Bearer {vapi_api_key}",
#             "Content-Type": "application/json"
#         }
        
#         # Make request to VAPI
#         async with httpx.AsyncClient() as client:
#             response = await client.get(url, headers=headers)
            
#             if response.status_code == 200:
#                 vapi_data = response.json()
                
#                 # VAPI returns a list directly, not an object with "calls" key
#                 call_logs = vapi_data if isinstance(vapi_data, list) else []
                
#                 # Convert to response format
#                 call_log_list = []
#                 for call_log in call_logs:
#                     call_data = {
#                         "id": call_log.get("id"),
#                         "assistant_id": call_log.get("assistantId"),
#                         "phone_number_id": call_log.get("phoneNumberId"),
#                         "status": call_log.get("status"),
#                         "started_at": call_log.get("startedAt"),
#                         "ended_at": call_log.get("endedAt"),
#                         "duration": call_log.get("duration"),
#                         "cost": call_log.get("cost"),
#                         "customer_number": call_log.get("customerNumber"),
#                         "customer_name": call_log.get("customerName"),
#                         "call_id": call_log.get("callId"),
#                         "ended_reason": call_log.get("endedReason"),
#                         "is_transferred": call_log.get("isTransferred"),
#                         "criteria_satisfied": call_log.get("criteriaSatisfied"),
#                         "summary": call_log.get("summary"),
#                         "transcript": call_log.get("transcript"),
#                         "analysis": call_log.get("analysis"),
#                         "recording_url": call_log.get("recordingUrl"),
#                         "created_at": call_log.get("createdAt"),
#                         "updated_at": call_log.get("updatedAt")
#                     }
#                     call_log_list.append(call_data)
                
#                 return {
#                     "success": True,
#                     "total_call_logs": len(call_log_list),
#                     "call_logs": call_log_list,
#                     "message": f"Successfully fetched {len(call_log_list)} call logs from VAPI"
#                 }
#             else:
#                 raise HTTPException(
#                     status_code=response.status_code,
#                     detail=f"Error fetching call logs from VAPI: {response.text}"
#                 )
                
#     except httpx.RequestError as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Network error while fetching call logs from VAPI: {str(e)}"
#         )
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Error fetching call logs from VAPI: {str(e)}"
#         )

# #/////////////////////////////////////////// Delete Call Log //////////////////////////////////////////////////////
# @admin_router.delete("/call-logs/{call_log_id}")
# async def delete_call_log(call_log_id: int, current_user: User = Depends(admin_required)):
#     """
#     Delete a call log from both local database and VAPI.
#     Only accessible by admin users.
#     """
#     try:
#         # Get the call log from local database
#         call_log = await CallLog.get_or_none(id=call_log_id)
#         if not call_log:
#             raise HTTPException(status_code=404, detail="Call log not found")
        
#         call_id = call_log.call_id
#         customer_name = call_log.customer_name
#         customer_number = call_log.customer_number
        
#         # Delete from VAPI if call_id exists
#         if call_id:
#             try:
#                 # Get VAPI credentials from environment
#                 vapi_api_key = os.environ.get("VAPI_API_KEY")
#                 vapi_org_id = os.environ.get("VAPI_ORG_ID")
                
#                 if not vapi_api_key or not vapi_org_id:
#                     raise HTTPException(
#                         status_code=500,
#                         detail="VAPI credentials not configured"
#                     )
                
#                 # VAPI API endpoint for call deletion
#                 url = f"https://api.vapi.ai/call/{call_id}"
#                 headers = {
#                     "Authorization": f"Bearer {vapi_api_key}",
#                     "Content-Type": "application/json"
#                 }
                
#                 # Make delete request to VAPI
#                 async with httpx.AsyncClient() as client:
#                     response = await client.delete(url, headers=headers)
                    
#                     if response.status_code in [200, 201, 204]:
#                         print(f"Successfully deleted call {call_id} from VAPI")
#                     else:
#                         print(f"Warning: Failed to delete call {call_id} from VAPI. Status: {response.status_code}")
                        
#             except Exception as e:
#                 print(f"Warning: Error deleting call {call_id} from VAPI: {str(e)}")
#                 # Continue with local deletion even if VAPI deletion fails
        
#         # Delete from local database
#         await call_log.delete()
        
#         return {
#             "success": True,
#             "detail": f"Call log for '{customer_name}' ({customer_number}) has been deleted successfully.",
#             "deleted_data": {
#                 "call_log_id": call_log_id,
#                 "call_id": call_id,
#                 "customer_name": customer_name,
#                 "customer_number": customer_number,
#                 "vapi_deleted": call_id is not None
#             }
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Error deleting call log: {str(e)}"
#         )


        
# #/////////////////////////////////////////// Delete Lead //////////////////////////////////////////////////////
# @admin_router.delete("/leads/{lead_id}")
# async def delete_lead(lead_id: int, current_user: User = Depends(admin_required)):
#     """
#     Delete a lead from the database.
#     Only accessible by admin users.
#     """
#     try:
#         lead = await Lead.get_or_none(id=lead_id)
#         if not lead:
#             raise HTTPException(status_code=404, detail="Lead not found")
        
#         # Delete the lead from the database
#         await lead.delete()
        
#         return {
#             "success": True,
#             "detail": f"Lead with ID {lead_id} has been deleted successfully."
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Error deleting lead: {str(e)}"
#         )


# #////////////////////////////// Knowledge Base ////////////////////////////////////////////////////
# @admin_router.get("/knowledge-base")
# async def get_all_knowledge_base(current_user: User = Depends(admin_required)):
#     """
#     Fetch all knowledge base documents and their details along with total count.
#     Only accessible by admin users.
#     """
#     try:
#         # Fetch all documents from the database
#         documents = await Documents.all().prefetch_related('user')
        
#         # Convert to response format
#         knowledge_base_list = []
#         for document in documents:
#             document_data = {
#                 "id": document.id,
#                 "file_name": document.file_name,
#                 "vapi_file_id": document.vapi_file_id,
#                 "user": {
#                     "id": document.user.id,
#                     "name": document.user.name,
#                     "email": document.user.email
#                 } if document.user else None
#             }
#             knowledge_base_list.append(document_data)
        
#         return {
#             "success": True,
#             "total_knowledge_base": len(knowledge_base_list),
#             "knowledge_base": knowledge_base_list,
#             "message": f"Successfully fetched {len(knowledge_base_list)} knowledge base documents"
#         }
        
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Error fetching knowledge base: {str(e)}"
#         )
# #/////////////////////////////////////////// Knowleddge base file from vapi Base ////////////////////////////////////////////
# @admin_router.get("/knowledge-base/file/{vapi_file_id}")
# async def get_vapi_file_details(vapi_file_id: str, current_user: User = Depends(admin_required)):
#     """
#     Fetch file details from VAPI using the vapi_file_id.
#     Only accessible by admin users.
#     """
#     try:
#         # Get VAPI credentials from environment
#         vapi_api_key = os.environ.get("VAPI_API_KEY")
#         vapi_org_id = os.environ.get("VAPI_ORG_ID")
        
#         if not vapi_api_key or not vapi_org_id:
#             raise HTTPException(
#                 status_code=500,
#                 detail="VAPI credentials not configured"
#             )
        
#         # VAPI API endpoint for file details
#         url = f"https://api.vapi.ai/file/{vapi_file_id}"
#         headers = {
#             "Authorization": f"Bearer {vapi_api_key}",
#             "Content-Type": "application/json"
#         }
        
#         # Make request to VAPI
#         async with httpx.AsyncClient() as client:
#             response = await client.get(url, headers=headers)
            
#             if response.status_code == 200:
#                 vapi_data = response.json()
                
#                 # Extract file details from VAPI response
#                 file_data = {
#                     "id": vapi_data.get("id"),
#                     "name": vapi_data.get("name"),
#                     "size": vapi_data.get("size"),
#                     "type": vapi_data.get("type"),
#                     "status": vapi_data.get("status"),
#                     "created_at": vapi_data.get("createdAt"),
#                     "updated_at": vapi_data.get("updatedAt"),
#                     "url": vapi_data.get("url"),
#                     "metadata": vapi_data.get("metadata", {}),
#                     "processing_status": vapi_data.get("processingStatus"),
#                     "file_type": vapi_data.get("fileType"),
#                     "mime_type": vapi_data.get("mimeType"),
#                     "file_size_bytes": vapi_data.get("fileSizeBytes"),
#                     "processing_error": vapi_data.get("processingError"),
#                     "is_processed": vapi_data.get("isProcessed", False)
#                 }
                
#                 return {
#                     "success": True,
#                     "file_details": file_data,
#                     "message": f"Successfully fetched file details for {vapi_file_id}"
#                 }
#             else:
#                 raise HTTPException(
#                     status_code=response.status_code,
#                     detail=f"Error fetching file details from VAPI: {response.text}"
#                 )
                
#     except httpx.RequestError as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Network error while fetching file details from VAPI: {str(e)}"
#         )
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Error fetching file details from VAPI: {str(e)}"
#         )
# #/////////////////////////////////////////// Delete Knowledge Base //////////////////////////////////////////////////////
# @admin_router.delete("/knowledge-base/{document_id}")
# async def delete_knowledge_base_file(document_id: int, current_user: User = Depends(admin_required)):
#     """
#     Delete a knowledge base file from both local database and VAPI.
#     Only accessible by admin users.
#     """
#     try:
#         # Get the document from local database
#         document = await Documents.get_or_none(id=document_id)
#         if not document:
#             raise HTTPException(status_code=404, detail="Knowledge base file not found")
        
#         vapi_file_id = document.vapi_file_id
#         file_name = document.file_name
        
#         # Delete from VAPI if vapi_file_id exists
#         if vapi_file_id:
#             try:
#                 # Get VAPI credentials from environment
#                 vapi_api_key = os.environ.get("VAPI_API_KEY")
#                 vapi_org_id = os.environ.get("VAPI_ORG_ID")
                
#                 if not vapi_api_key or not vapi_org_id:
#                     raise HTTPException(
#                         status_code=500,
#                         detail="VAPI credentials not configured"
#                     )
                
#                 # VAPI API endpoint for file deletion
#                 url = f"https://api.vapi.ai/file/{vapi_file_id}"
#                 headers = {
#                     "Authorization": f"Bearer {vapi_api_key}",
#                     "Content-Type": "application/json"
#                 }
                
#                 # Make delete request to VAPI
#                 async with httpx.AsyncClient() as client:
#                     response = await client.delete(url, headers=headers)
                    
#                     if response.status_code in [200, 201, 204]:
#                         print(f"Successfully deleted file {vapi_file_id} from VAPI")
#                     else:
#                         print(f"Warning: Failed to delete file {vapi_file_id} from VAPI. Status: {response.status_code}")
                        
#             except Exception as e:
#                 print(f"Warning: Error deleting file {vapi_file_id} from VAPI: {str(e)}")
#                 # Continue with local deletion even if VAPI deletion fails
        
#         # Delete from local database
#         await document.delete()
        
#         return {
#             "success": True,
#             "detail": f"Knowledge base file '{file_name}' has been deleted successfully.",
#             "deleted_data": {
#                 "document_id": document_id,
#                 "file_name": file_name,
#                 "vapi_file_id": vapi_file_id,
#                 "vapi_deleted": vapi_file_id is not None
#             }
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Error deleting knowledge base file: {str(e)}"
#         )
















# second update













# from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
# from fastapi.responses import Response
# from pydantic import BaseModel, EmailStr
# from models.auth import User  # Code no longer used here
# from models.purchased_numbers import PurchasedNumber
# from models.assistant import Assistant
# from models.lead import Lead
# from models.call_log import CallLog
# from models.documents import Documents
# from helpers.token_helper import admin_required
# from helpers.vapi_helper import get_headers
# from passlib.context import CryptContext
# from datetime import datetime, timedelta
# import secrets
# import string
# import os
# import httpx
# from dotenv import load_dotenv
# import requests
# import pathlib
# import imghdr

# load_dotenv()

# admin_router = APIRouter()

# # ───────────────────────────────────────────────────────────────────────────────
# # Profile-photo helpers (FS + DB via user.profile_photo)
# # Target folder: media/profile_photos
# # Public base URL: /media/profile_photos
# # ───────────────────────────────────────────────────────────────────────────────

# ALLOWED_EXTS = [".jpg", ".jpeg", ".png", ".webp"]
# ALLOWED_MIME_TO_EXT = {
#     "image/jpeg": ".jpg",
#     "image/png": ".png",
#     "image/webp": ".webp",
# }
# MAX_PROFILE_PHOTO_BYTES = 5 * 1024 * 1024  # 5MB

# def _profile_dir() -> pathlib.Path:
#     p = pathlib.Path(os.environ.get("PROFILE_PHOTOS_DIR", "media/profile_photos"))
#     p.mkdir(parents=True, exist_ok=True)
#     return p

# def _profile_base_url() -> str:
#     val = os.environ.get("PROFILE_PHOTOS_BASE_URL", "/media/profile_photos")
#     return val.rstrip("/")

# def _url_for_filename(name: str | None) -> str | None:
#     if not name:
#         return None
#     return f"{_profile_base_url()}/{name}"

# def _existing_profile_photo_path(user_id: int) -> pathlib.Path | None:
#     base = _profile_dir()
#     for ext in [".jpg", ".jpeg", ".png", ".webp"]:
#         candidate = base / f"user_{user_id}{ext}"
#         if candidate.exists():
#             return candidate
#     return None

# def _guess_ext(filename: str, content_type: str | None, data: bytes) -> str:
#     if content_type in ALLOWED_MIME_TO_EXT:
#         return ALLOWED_MIME_TO_EXT[content_type]
#     ext = pathlib.Path(filename or "").suffix.lower()
#     if ext in ALLOWED_EXTS:
#         return ".jpg" if ext == ".jpeg" else ext
#     kind = imghdr.what(None, h=data)
#     if kind == "jpeg":
#         return ".jpg"
#     if kind in ("png", "webp"):
#         return f".{kind}"
#     raise HTTPException(status_code=400, detail="Unsupported image type. Use JPG/PNG/WebP.")

# def _profile_photo_url_for_user(user_id: int, db_value: str | None) -> str | None:
#     if db_value:
#         if db_value.startswith("/") or db_value.startswith("http"):
#             return db_value
#         try:
#             name = pathlib.Path(db_value).name
#             if name:
#                 return _url_for_filename(name)
#         except Exception:
#             pass
#     p = _existing_profile_photo_path(user_id)
#     return _url_for_filename(p.name) if p else None

# # ───────────────────────────────────────────────────────────────────────────────
# # Password helpers
# # ───────────────────────────────────────────────────────────────────────────────

# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# def _hash_password(plain: str) -> str:
#     return pwd_context.hash(plain)

# def _gen_password(length: int = 12) -> str:
#     alphabet = string.ascii_letters + string.digits
#     return "".join(secrets.choice(alphabet) for _ in range(length))

# # ───────────────────────────────────────────────────────────────────────────────
# # Schemas
# # ───────────────────────────────────────────────────────────────────────────────

# class AdminCreateUserRequest(BaseModel):
#     name: str
#     email: EmailStr
#     role: str = "user"          # "user" | "admin"
#     password: str | None = None # optional; auto-generated if not provided

# class AdminBulkCreateUsersRequest(BaseModel):
#     users: list[AdminCreateUserRequest]

# class AdminResetPasswordRequest(BaseModel):
#     new_password: str | None = None  # if omitted, auto-generate

# class UserUpdateRequest(BaseModel):
#     name: str
#     email: str
#     role: str

# # ───────────────────────────────────────────────────────────────────────────────
# # Users
# # ───────────────────────────────────────────────────────────────────────────────

# @admin_router.get("/users")
# async def get_all_users(current_user: User = Depends(admin_required)):
#     try:
#         users = await User.all()
#         user_list = []
#         for user in users:
#             user_list.append({
#                 "id": user.id,
#                 "name": user.name,
#                 "email": user.email,
#                 "email_verified": user.email_verified,
#                 "role": getattr(user, "role", "user"),
#                 "profile_photo": getattr(user, "profile_photo", None),
#                 "profile_photo_url": _profile_photo_url_for_user(user.id, getattr(user, "profile_photo", None)),
#             })
#         return {
#             "success": True,
#             "total_users": len(user_list),
#             "users": user_list,
#             "message": f"Successfully fetched {len(user_list)} users"
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error fetching users: {str(e)}")

# @admin_router.put("/users/{user_id}")
# async def update_user(user_id: int, user_data: UserUpdateRequest, current_user: User = Depends(admin_required)):
#     try:
#         name = user_data.name
#         email = user_data.email
#         role = user_data.role

#         valid_roles = ["user", "admin"]
#         if role not in valid_roles:
#             raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}")

#         user = await User.get_or_none(id=user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         existing_user = await User.filter(email=email).exclude(id=user_id).first()
#         if existing_user:
#             raise HTTPException(status_code=400, detail="Email is already taken by another user")

#         user.name = name
#         user.email = email
#         user.role = role
#         await user.save()

#         return {
#             "success": True,
#             "detail": f"User with ID {user_id} has been updated successfully.",
#             "updated_user": {
#                 "id": user.id,
#                 "name": user.name,
#                 "email": user.email,
#                 "email_verified": user.email_verified,
#                 "role": user.role,
#                 "profile_photo": getattr(user, "profile_photo", None),
#                 "profile_photo_url": _profile_photo_url_for_user(user.id, getattr(user, "profile_photo", None)),
#             }
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error updating user: {str(e)}")

# # Manage delete alias
# @admin_router.delete("/manage/user-accounts/{user_id}")
# async def manage_delete_user_account(user_id: int, current_user: User = Depends(admin_required)):
#     return await delete_user(user_id, current_user)

# @admin_router.delete("/users/{user_id}")
# async def delete_user(user_id: int, current_user: User = Depends(admin_required)):
#     try:
#         user = await User.get_or_none(id=user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         if user.id == current_user.id:
#             raise HTTPException(status_code=400, detail="You cannot delete your own account")

#         assistants_count = await Assistant.filter(user=user).count()
#         call_logs_count = await CallLog.filter(user=user).count()
#         purchased_numbers_count = await PurchasedNumber.filter(user=user).count()

#         assistants = await Assistant.filter(user=user).all()
#         for assistant in assistants:
#             try:
#                 if assistant.vapi_phone_uuid:
#                     requests.patch(
#                         f"https://api.vapi.ai/phone-number/{assistant.vapi_phone_uuid}",
#                         json={"assistantId": None},
#                         headers=get_headers()
#                     ).raise_for_status()

#                 vapi_assistant_id = assistant.vapi_assistant_id
#                 vapi_url = f"{os.environ.get('VAPI_URL', 'https://api.vapi.ai/assistant')}/{vapi_assistant_id}"
#                 requests.delete(vapi_url, headers=get_headers())
#             except Exception as e:
#                 print(f"Warning: Failed to delete assistant {assistant.id} from VAPI: {str(e)}")

#             await assistant.delete()

#         await CallLog.filter(user=user).delete()
#         await PurchasedNumber.filter(user=user).delete()

#         try:
#             from models.file import File
#             user_files = await File.filter(user=user).all()
#             file_ids = [file.id for file in user_files]
#             if file_ids:
#                 await Lead.filter(file_id__in=file_ids).delete()
#             await File.filter(user=user).delete()
#         except Exception as e:
#             print(f"Warning: Error deleting user files and associated leads: {str(e)}")

#         # Profile photo cleanup (FS)
#         try:
#             p = _existing_profile_photo_path(user.id)
#             if p:
#                 p.unlink(missing_ok=True)
#         except Exception as e:
#             print(f"Warning: Error deleting profile photo for user {user.id}: {str(e)}")

#         await user.delete()

#         return {
#             "success": True,
#             "detail": f"User with ID {user_id} and all related data have been deleted successfully.",
#             "deleted_data": {
#                 "assistants": assistants_count,
#                 "call_logs": call_logs_count,
#                 "purchased_numbers": purchased_numbers_count,
#                 "files_and_leads": "deleted"
#             }
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error deleting user: {str(e)}")

# # ───────────────────────────────────────────────────────────────────────────────
# # Phone Numbers
# # ───────────────────────────────────────────────────────────────────────────────

# @admin_router.get("/phone-numbers")
# async def get_all_phone_numbers(current_user: User = Depends(admin_required)):
#     try:
#         phone_numbers = await PurchasedNumber.all().prefetch_related('user')
#         phone_number_list = []
#         for phone_number in phone_numbers:
#             phone_number_list.append({
#                 "id": phone_number.id,
#                 "phone_number": phone_number.phone_number,
#                 "friendly_name": phone_number.friendly_name,
#                 "region": phone_number.region,
#                 "postal_code": phone_number.postal_code,
#                 "iso_country": phone_number.iso_country,
#                 "last_month_payment": phone_number.last_month_payment,
#                 "created_at": phone_number.created_at,
#                 "updated_at": phone_number.updated_at,
#                 "attached_assistant": phone_number.attached_assistant,
#                 "vapi_phone_uuid": phone_number.vapi_phone_uuid,
#                 "user": {
#                     "id": phone_number.user.id,
#                     "name": phone_number.user.name,
#                     "email": phone_number.user.email
#                 } if phone_number.user else None
#             })
#         return {
#             "success": True,
#             "total_phone_numbers": len(phone_number_list),
#             "phone_numbers": phone_number_list,
#             "message": f"Successfully fetched {len(phone_number_list)} phone numbers"
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error fetching phone numbers: {str(e)}")

# @admin_router.delete("/phone-numbers/{phone_number_id}")
# async def delete_phone_number(phone_number_id: int, current_user: User = Depends(admin_required)):
#     try:
#         phone_number = await PurchasedNumber.get_or_none(id=phone_number_id)
#         if not phone_number:
#             raise HTTPException(status_code=404, detail="Phone number not found")

#         vapi_phone_uuid = phone_number.vapi_phone_uuid
#         phone_number_value = phone_number.phone_number

#         if phone_number.attached_assistant:
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"Cannot delete phone number '{phone_number_value}' as it is currently attached to an assistant. Please detach it first."
#             )

#         if vapi_phone_uuid:
#             try:
#                 vapi_api_key = os.environ.get("VAPI_API_KEY")
#                 vapi_org_id = os.environ.get("VAPI_ORG_ID")
#                 if not vapi_api_key or not vapi_org_id:
#                     raise HTTPException(status_code=500, detail="VAPI credentials not configured")

#                 url = f"https://api.vapi.ai/phone-number/{vapi_phone_uuid}"
#                 headers = {"Authorization": f"Bearer {vapi_api_key}", "Content-Type": "application/json"}
#                 async with httpx.AsyncClient() as client:
#                     response = await client.delete(url, headers=headers)
#                     if response.status_code in [200, 201, 204]:
#                         print(f"Successfully deleted phone number {vapi_phone_uuid} from VAPI")
#                     else:
#                         print(f"Warning: Failed to delete phone number {vapi_phone_uuid} from VAPI. Status: {response.status_code}")
#             except Exception as e:
#                 print(f"Warning: Error deleting phone number {vapi_phone_uuid} from VAPI: {str(e)}")

#         await phone_number.delete()

#         return {
#             "success": True,
#             "detail": f"Phone number '{phone_number_value}' has been deleted successfully.",
#             "deleted_data": {
#                 "phone_number_id": phone_number_id,
#                 "phone_number": phone_number_value,
#                 "vapi_phone_uuid": vapi_phone_uuid,
#                 "vapi_deleted": vapi_phone_uuid is not None
#             }
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error deleting phone number: {str(e)}")

# # ───────────────────────────────────────────────────────────────────────────────
# # Assistants
# # ───────────────────────────────────────────────────────────────────────────────

# @admin_router.get("/assistants")
# async def get_all_assistants(current_user: User = Depends(admin_required)):
#     try:
#         assistants = await Assistant.all().prefetch_related('user')
#         assistant_list = []
#         for assistant in assistants:
#             assistant_list.append({
#                 "id": assistant.id,
#                 "vapi_assistant_id": assistant.vapi_assistant_id,
#                 "name": assistant.name,
#                 "provider": assistant.provider,
#                 "first_message": assistant.first_message,
#                 "model": assistant.model,
#                 "systemPrompt": assistant.systemPrompt,
#                 "knowledgeBase": assistant.knowledgeBase,
#                 "leadsfile": assistant.leadsfile,
#                 "temperature": assistant.temperature,
#                 "maxTokens": assistant.maxTokens,
#                 "transcribe_provider": assistant.transcribe_provider,
#                 "transcribe_language": assistant.transcribe_language,
#                 "transcribe_model": assistant.transcribe_model,
#                 "voice_provider": assistant.voice_provider,
#                 "voice": assistant.voice,
#                 "forwardingPhoneNumber": assistant.forwardingPhoneNumber,
#                 "endCallPhrases": assistant.endCallPhrases,
#                 "attached_Number": assistant.attached_Number,
#                 "vapi_phone_uuid": assistant.vapi_phone_uuid,
#                 "draft": assistant.draft,
#                 "assistant_toggle": assistant.assistant_toggle,
#                 "success_evalution": assistant.success_evalution,
#                 "category": assistant.category,
#                 "voice_model": assistant.voice_model,
#                 "languages": assistant.languages,
#                 "created_at": assistant.created_at,
#                 "updated_at": assistant.updated_at,
#                 "speed": assistant.speed,
#                 "stability": assistant.stability,
#                 "similarityBoost": assistant.similarityBoost,
#                 "user": {
#                     "id": assistant.user.id,
#                     "name": assistant.user.name,
#                     "email": assistant.user.email
#                 } if assistant.user else None
#             })
#         return {
#             "success": True,
#             "total_assistants": len(assistant_list),
#             "assistants": assistant_list,
#             "message": f"Successfully fetched {len(assistant_list)} assistants"
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error fetching assistants: {str(e)}")

# @admin_router.delete("/assistants/{assistant_id}")
# async def delete_assistant(assistant_id: int, current_user: User = Depends(admin_required)):
#     try:
#         assistant = await Assistant.get_or_none(id=assistant_id)
#         if not assistant:
#             raise HTTPException(status_code=404, detail="Assistant not found")

#         if assistant.vapi_phone_uuid:
#             try:
#                 requests.patch(
#                     f"https://api.vapi.ai/phone-number/{assistant.vapi_phone_uuid}",
#                     json={"assistantId": None},
#                     headers=get_headers()
#                 ).raise_for_status()
#             except Exception as e:
#                 print(f"Warning: Failed to detach phone number from VAPI: {str(e)}")

#         if assistant.attached_Number:
#             phone_number = await PurchasedNumber.get_or_none(attached_assistant=assistant_id)
#             if phone_number:
#                 await PurchasedNumber.filter(attached_assistant=assistant_id).update(attached_assistant=None)

#         vapi_assistant_id = assistant.vapi_assistant_id
#         vapi_url = f"{os.environ.get('VAPI_URL', 'https://api.vapi.ai/assistant')}/{vapi_assistant_id}"

#         try:
#             response = requests.delete(vapi_url, headers=get_headers())
#             if response.status_code in [200, 201, 204]:
#                 await assistant.delete()
#                 return {"success": True, "detail": "Assistant deleted from VAPI and local DB."}
#             else:
#                 await assistant.delete()
#                 return {
#                     "success": True,
#                     "detail": f"Assistant deleted locally. VAPI deletion failed with status {response.status_code}: {response.text}"
#                 }
#         except Exception as e:
#             await assistant.delete()
#             return {"success": True, "detail": f"Assistant deleted locally. VAPI deletion failed: {str(e)}"}

#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error deleting assistant: {str(e)}")

# # ───────────────────────────────────────────────────────────────────────────────
# # Leads
# # ───────────────────────────────────────────────────────────────────────────────

# @admin_router.get("/leadss")
# async def get_all_leads(current_user: User = Depends(admin_required)):
#     try:
#         leads = await Lead.all()
#         lead_list = []
#         for lead in leads:
#             lead_list.append({
#                 "id": lead.id,
#                 "first_name": lead.first_name,
#                 "last_name": lead.last_name,
#                 "email": lead.email,
#                 "add_date": lead.add_date,
#                 "salesforce_id": lead.salesforce_id,
#                 "mobile": lead.mobile,
#                 "state": lead.state,
#                 "timezone": lead.timezone,
#                 "dnc": lead.dnc,
#                 "submit_for_approval": lead.submit_for_approval,
#                 "other_data": lead.other_data,
#                 "last_called_at": lead.last_called_at,
#                 "call_count": lead.call_count,
#                 "created_at": lead.created_at,
#                 "updated_at": lead.updated_at
#             })
#         return {
#             "success": True,
#             "total_leads": len(lead_list),
#             "leads": lead_list,
#             "message": f"Successfully fetched {len(lead_list)} leads"
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error fetching leads: {str(e)}")

# class LeadUpdateRequest(BaseModel):
#     first_name: str
#     last_name: str
#     email: str
#     add_date: str  # YYYY-MM-DD
#     salesforce_id: str | None = None
#     mobile: str
#     state: str | None = None
#     timezone: str | None = None
#     dnc: bool = False
#     submit_for_approval: bool = False
#     other_data: dict | None = None
#     call_count: int = 0

# @admin_router.put("/leads/{lead_id}")
# async def update_lead(lead_id: int, lead_data: LeadUpdateRequest, current_user: User = Depends(admin_required)):
#     try:
#         from datetime import datetime
#         lead = await Lead.get_or_none(id=lead_id)
#         if not lead:
#             raise HTTPException(status_code=404, detail="Lead not found")

#         try:
#             add_date = datetime.strptime(lead_data.add_date, "%Y-%m-%d").date()
#         except ValueError:
#             raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD format")

#         lead.first_name = lead_data.first_name
#         lead.last_name = lead_data.last_name
#         lead.email = lead_data.email
#         lead.add_date = add_date
#         lead.salesforce_id = lead_data.salesforce_id
#         lead.mobile = lead_data.mobile
#         lead.state = lead_data.state
#         lead.timezone = lead_data.timezone
#         lead.dnc = lead_data.dnc
#         lead.submit_for_approval = lead_data.submit_for_approval
#         lead.other_data = lead_data.other_data
#         lead.call_count = lead_data.call_count
#         await lead.save()

#         return {
#             "success": True,
#             "detail": f"Lead with ID {lead_id} has been updated successfully.",
#             "updated_lead": {
#                 "id": lead.id,
#                 "first_name": lead.first_name,
#                 "last_name": lead.last_name,
#                 "email": lead.email,
#                 "add_date": lead.add_date.isoformat(),
#                 "salesforce_id": lead.salesforce_id,
#                 "mobile": lead.mobile,
#                 "state": lead.state,
#                 "timezone": lead.timezone,
#                 "dnc": lead.dnc,
#                 "submit_for_approval": lead.submit_for_approval,
#                 "other_data": lead.other_data,
#                 "last_called_at": lead.last_called_at.isoformat() if lead.last_called_at else None,
#                 "call_count": lead.call_count,
#                 "created_at": lead.created_at.isoformat(),
#                 "updated_at": lead.updated_at.isoformat()
#             }
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error updating lead: {str(e)}")

# # ───────────────────────────────────────────────────────────────────────────────
# # Call logs
# # ───────────────────────────────────────────────────────────────────────────────

# @admin_router.get("/call-logs")
# async def get_all_call_logs(current_user: User = Depends(admin_required)):
#     try:
#         call_logs = await CallLog.all().prefetch_related('user')
#         call_log_list = []
#         for call_log in call_logs:
#             call_log_list.append({
#                 "id": call_log.id,
#                 "lead_id": call_log.lead_id,
#                 "call_started_at": call_log.call_started_at,
#                 "customer_number": call_log.customer_number,
#                 "customer_name": call_log.customer_name,
#                 "call_id": call_log.call_id,
#                 "cost": call_log.cost,
#                 "call_ended_at": call_log.call_ended_at,
#                 "call_ended_reason": call_log.call_ended_reason,
#                 "call_duration": call_log.call_duration,
#                 "is_transferred": call_log.is_transferred,
#                 "status": call_log.status,
#                 "criteria_satisfied": call_log.criteria_satisfied,
#                 "user": {
#                     "id": call_log.user.id,
#                     "name": call_log.user.name,
#                     "email": call_log.user.email
#                 } if call_log.user else None
#             })
#         return {
#             "success": True,
#             "total_call_logs": len(call_log_list),
#             "call_logs": call_log_list,
#             "message": f"Successfully fetched {len(call_log_list)} call logs"
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error fetching call logs: {str(e)}")

# @admin_router.get("/vapi-call-logs")
# async def get_vapi_call_logs(current_user: User = Depends(admin_required)):
#     try:
#         vapi_api_key = os.environ.get("VAPI_API_KEY")
#         vapi_org_id = os.environ.get("VAPI_ORG_ID")
#         if not vapi_api_key or not vapi_org_id:
#             raise HTTPException(status_code=500, detail="VAPI credentials not configured")

#         url = "https://api.vapi.ai/call/"
#         headers = {"Authorization": f"Bearer {vapi_api_key}", "Content-Type": "application/json"}

#         async with httpx.AsyncClient() as client:
#             response = await client.get(url, headers=headers)
#             if response.status_code == 200:
#                 vapi_data = response.json()
#                 call_logs = vapi_data if isinstance(vapi_data, list) else []
#                 call_log_list = []
#                 for call_log in call_logs:
#                     call_log_list.append({
#                         "id": call_log.get("id"),
#                         "assistant_id": call_log.get("assistantId"),
#                         "phone_number_id": call_log.get("phoneNumberId"),
#                         "status": call_log.get("status"),
#                         "started_at": call_log.get("startedAt"),
#                         "ended_at": call_log.get("endedAt"),
#                         "duration": call_log.get("duration"),
#                         "cost": call_log.get("cost"),
#                         "customer_number": call_log.get("customerNumber"),
#                         "customer_name": call_log.get("customerName"),
#                         "call_id": call_log.get("callId"),
#                         "ended_reason": call_log.get("endedReason"),
#                         "is_transferred": call_log.get("isTransferred"),
#                         "criteria_satisfied": call_log.get("criteriaSatisfied"),
#                         "summary": call_log.get("summary"),
#                         "transcript": call_log.get("transcript"),
#                         "analysis": call_log.get("analysis"),
#                         "recording_url": call_log.get("recordingUrl"),
#                         "created_at": call_log.get("createdAt"),
#                         "updated_at": call_log.get("UpdatedAt") or call_log.get("updatedAt")
#                     })
#                 return {
#                     "success": True,
#                     "total_call_logs": len(call_log_list),
#                     "call_logs": call_log_list,
#                     "message": f"Successfully fetched {len(call_log_list)} call logs from VAPI"
#                 }
#             else:
#                 raise HTTPException(status_code=response.status_code, detail=f"Error fetching call logs from VAPI: {response.text}")

#     except httpx.RequestError as e:
#         raise HTTPException(status_code=500, detail=f"Network error while fetching call logs from VAPI: {str(e)}")
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error fetching call logs from VAPI: {str(e)}")

# @admin_router.delete("/call-logs/{call_log_id}")
# async def delete_call_log(call_log_id: int, current_user: User = Depends(admin_required)):
#     try:
#         call_log = await CallLog.get_or_none(id=call_log_id)
#         if not call_log:
#             raise HTTPException(status_code=404, detail="Call log not found")

#         call_id = call_log.call_id
#         customer_name = call_log.customer_name
#         customer_number = call_log.customer_number

#         if call_id:
#             try:
#                 vapi_api_key = os.environ.get("VAPI_API_KEY")
#                 vapi_org_id = os.environ.get("VAPI_ORG_ID")
#                 if not vapi_api_key or not vapi_org_id:
#                     raise HTTPException(status_code=500, detail="VAPI credentials not configured")

#                 url = f"https://api.vapi.ai/call/{call_id}"
#                 headers = {"Authorization": f"Bearer {vapi_api_key}", "Content-Type": "application/json"}
#                 async with httpx.AsyncClient() as client:
#                     response = await client.delete(url, headers=headers)
#                     if response.status_code in [200, 201, 204]:
#                         print(f"Successfully deleted call {call_id} from VAPI")
#                     else:
#                         print(f"Warning: Failed to delete call {call_id} from VAPI. Status: {response.status_code}")
#             except Exception as e:
#                 print(f"Warning: Error deleting call {call_id} from VAPI: {str(e)}")

#         await call_log.delete()

#         return {
#             "success": True,
#             "detail": f"Call log for '{customer_name}' ({customer_number}) has been deleted successfully.",
#             "deleted_data": {
#                 "call_log_id": call_log_id,
#                 "call_id": call_id,
#                 "customer_name": customer_name,
#                 "customer_number": customer_number,
#                 "vapi_deleted": call_id is not None
#             }
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error deleting call log: {str(e)}")

# # ───────────────────────────────────────────────────────────────────────────────
# # Knowledge Base
# # ───────────────────────────────────────────────────────────────────────────────

# @admin_router.get("/knowledge-base")
# async def get_all_knowledge_base(current_user: User = Depends(admin_required)):
#     try:
#         documents = await Documents.all().prefetch_related('user')
#         knowledge_base_list = []
#         for document in documents:
#             knowledge_base_list.append({
#                 "id": document.id,
#                 "file_name": document.file_name,
#                 "vapi_file_id": document.vapi_file_id,
#                 "user": {
#                     "id": document.user.id,
#                     "name": document.user.name,
#                     "email": document.user.email
#                 } if document.user else None
#             })
#         return {
#             "success": True,
#             "total_knowledge_base": len(knowledge_base_list),
#             "knowledge_base": knowledge_base_list,
#             "message": f"Successfully fetched {len(knowledge_base_list)} knowledge base documents"
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error fetching knowledge base: {str(e)}")

# @admin_router.get("/knowledge-base/file/{vapi_file_id}")
# async def get_vapi_file_details(vapi_file_id: str, current_user: User = Depends(admin_required)):
#     try:
#         vapi_api_key = os.environ.get("VAPI_API_KEY")
#         vapi_org_id = os.environ.get("VAPI_ORG_ID")
#         if not vapi_api_key or not vapi_org_id:
#             raise HTTPException(status_code=500, detail="VAPI credentials not configured")

#         url = f"https://api.vapi.ai/file/{vapi_file_id}"
#         headers = {"Authorization": f"Bearer {vapi_api_key}", "Content-Type": "application/json"}

#         async with httpx.AsyncClient() as client:
#             response = await client.get(url, headers=headers)
#             if response.status_code == 200:
#                 vapi_data = response.json()
#                 file_data = {
#                     "id": vapi_data.get("id"),
#                     "name": vapi_data.get("name"),
#                     "size": vapi_data.get("size"),
#                     "type": vapi_data.get("type"),
#                     "status": vapi_data.get("status"),
#                     "created_at": vapi_data.get("createdAt"),
#                     "updated_at": vapi_data.get("updatedAt"),
#                     "url": vapi_data.get("url"),
#                     "metadata": vapi_data.get("metadata", {}),
#                     "processing_status": vapi_data.get("processingStatus"),
#                     "file_type": vapi_data.get("fileType"),
#                     "mime_type": vapi_data.get("mimeType"),
#                     "file_size_bytes": vapi_data.get("fileSizeBytes"),
#                     "processing_error": vapi_data.get("processingError"),
#                     "is_processed": vapi_data.get("isProcessed", False)
#                 }
#                 return {"success": True, "file_details": file_data, "message": f"Successfully fetched file details for {vapi_file_id}"}
#             else:
#                 raise HTTPException(status_code=response.status_code, detail=f"Error fetching file details from VAPI: {response.text}")

#     except httpx.RequestError as e:
#         raise HTTPException(status_code=500, detail=f"Network error while fetching file details from VAPI: {str(e)}")
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error fetching file details from VAPI: {str(e)}")

# @admin_router.delete("/knowledge-base/{document_id}")
# async def delete_knowledge_base_file(document_id: int, current_user: User = Depends(admin_required)):
#     try:
#         document = await Documents.get_or_none(id=document_id)
#         if not document:
#             raise HTTPException(status_code=404, detail="Knowledge base file not found")

#         vapi_file_id = document.vapi_file_id
#         file_name = document.file_name

#         if vapi_file_id:
#             try:
#                 vapi_api_key = os.environ.get("VAPI_API_KEY")
#                 vapi_org_id = os.environ.get("VAPI_ORG_ID")
#                 if not vapi_api_key or not vapi_org_id:
#                     raise HTTPException(status_code=500, detail="VAPI credentials not configured")

#                 url = f"https://api.vapi.ai/file/{vapi_file_id}"
#                 headers = {"Authorization": f"Bearer {vapi_api_key}", "Content-Type": "application/json"}
#                 async with httpx.AsyncClient() as client:
#                     response = await client.delete(url, headers=headers)
#                     if response.status_code in [200, 201, 204]:
#                         print(f"Successfully deleted file {vapi_file_id} from VAPI")
#                     else:
#                         print(f"Warning: Failed to delete file {vapi_file_id} from VAPI. Status: {response.status_code}")
#             except Exception as e:
#                 print(f"Warning: Error deleting file {vapi_file_id} from VAPI: {str(e)}")

#         await document.delete()

#         return {
#             "success": True,
#             "detail": f"Knowledge base file '{file_name}' has been deleted successfully.",
#             "deleted_data": {
#                 "document_id": document_id,
#                 "file_name": file_name,
#                 "vapi_file_id": vapi_file_id,
#                 "vapi_deleted": vapi_file_id is not None
#             }
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error deleting knowledge base file: {str(e)}")

# # ───────────────────────────────────────────────────────────────────────────────
# # Profile photo (self + admin)
# # ───────────────────────────────────────────────────────────────────────────────

# @admin_router.put("/me/profile-photo")
# async def upload_or_update_my_profile_photo(
#     file: UploadFile = File(...),
#     current_user: User = Depends(admin_required),
# ):
#     data = await file.read()
#     if not data:
#         raise HTTPException(status_code=400, detail="Empty file.")
#     if len(data) > MAX_PROFILE_PHOTO_BYTES:
#         raise HTTPException(status_code=400, detail="File too large (max 5MB).")

#     ext = _guess_ext(file.filename, file.content_type, data)
#     dst_dir = _profile_dir()

#     old = _existing_profile_photo_path(current_user.id)
#     if old and old.suffix.lower() != ext:
#         try:
#             old.unlink(missing_ok=True)
#         except Exception:
#             pass

#     dst = dst_dir / f"user_{current_user.id}{ext}"
#     try:
#         with open(dst, "wb") as f:
#             f.write(data)
#     finally:
#         await file.close()

#     photo_url = _url_for_filename(dst.name)
#     current_user.profile_photo = photo_url
#     await current_user.save()

#     return {
#         "success": True,
#         "detail": "Profile photo uploaded.",
#         "file_name": dst.name,
#         "file_path": str(dst),
#         "profile_photo": photo_url,
#         "profile_photo_url": photo_url,
#     }

# @admin_router.get("/me/profile-photo")
# async def get_my_profile_photo(current_user: User = Depends(admin_required)):
#     p = _existing_profile_photo_path(current_user.id)
#     url = _profile_photo_url_for_user(current_user.id, current_user.profile_photo)
#     return {
#         "success": True,
#         "exists": (p is not None) or bool(url),
#         "db_value": current_user.profile_photo,
#         "file_name": p.name if p else (pathlib.Path(current_user.profile_photo).name if (current_user.profile_photo and not current_user.profile_photo.startswith("/")) else None),
#         "file_path": str(p) if p else None,
#         "profile_photo_url": url,
#     }

# @admin_router.get("/me/profile-photo/raw")
# async def get_my_profile_photo_raw(current_user: User = Depends(admin_required)):
#     p = _existing_profile_photo_path(current_user.id)
#     if p and p.exists():
#         mt = "image/jpeg" if p.suffix.lower() in [".jpg", ".jpeg"] else "image/png" if p.suffix.lower() == ".png" else "image/webp"
#         return Response(content=p.read_bytes(), media_type=mt)
#     raise HTTPException(status_code=404, detail="Profile photo not found.")

# @admin_router.delete("/me/profile-photo")
# async def delete_my_profile_photo(current_user: User = Depends(admin_required)):
#     p = _existing_profile_photo_path(current_user.id)
#     if p:
#         try:
#             p.unlink(missing_ok=True)
#         except Exception as e:
#             raise HTTPException(status_code=500, detail=f"Failed to delete photo: {str(e)}")

#     current_user.profile_photo = None
#     await current_user.save()
#     return {"success": True, "detail": "Profile photo deleted."}

# @admin_router.get("/users/{user_id}/profile-photo")
# async def admin_get_user_profile_photo(user_id: int, current_user: User = Depends(admin_required)):
#     user = await User.get_or_none(id=user_id)
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")
#     p = _existing_profile_photo_path(user_id)
#     url = _profile_photo_url_for_user(user_id, user.profile_photo)
#     return {
#         "success": True,
#         "exists": (p is not None) or bool(url),
#         "db_value": user.profile_photo,
#         "file_name": p.name if p else (pathlib.Path(user.profile_photo).name if (user.profile_photo and not user.profile_photo.startswith("/")) else None),
#         "file_path": str(p) if p else None,
#         "profile_photo_url": url,
#     }

# @admin_router.get("/users/{user_id}/profile-photo/raw")
# async def admin_get_user_profile_photo_raw(user_id: int, current_user: User = Depends(admin_required)):
#     user = await User.get_or_none(id=user_id)
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")
#     p = _existing_profile_photo_path(user_id)
#     if p and p.exists():
#         mt = "image/jpeg" if p.suffix.lower() in [".jpg", ".jpeg"] else "image/png" if p.suffix.lower() == ".png" else "image/webp"
#         return Response(content=p.read_bytes(), media_type=mt)
#     raise HTTPException(status_code=404, detail="Profile photo not found.")

# @admin_router.delete("/users/{user_id}/profile-photo")
# async def admin_delete_user_profile_photo(user_id: int, current_user: User = Depends(admin_required)):
#     user = await User.get_or_none(id=user_id)
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")
#     p = _existing_profile_photo_path(user_id)
#     if p:
#         try:
#             p.unlink(missing_ok=True)
#         except Exception as e:
#             raise HTTPException(status_code=500, detail=f"Failed to delete photo: {str(e)}")
#     user.profile_photo = None
#     await user.save()
#     return {"success": True, "detail": f"Deleted profile photo for user {user_id}."}

# # ───────────────────────────────────────────────────────────────────────────────
# # “Main” user-details endpoints (deep export)
# # ───────────────────────────────────────────────────────────────────────────────

# async def _collect_user_details(user: User) -> dict:
#     numbers = await PurchasedNumber.filter(user=user).all()
#     numbers_payload = [{
#         "id": n.id,
#         "phone_number": n.phone_number,
#         "friendly_name": n.friendly_name,
#         "region": n.region,
#         "postal_code": n.postal_code,
#         "iso_country": n.iso_country,
#         "last_month_payment": n.last_month_payment,
#         "attached_assistant": n.attached_assistant,
#         "vapi_phone_uuid": n.vapi_phone_uuid,
#         "created_at": n.created_at,
#         "updated_at": n.updated_at,
#     } for n in numbers]

#     assistants = await Assistant.filter(user=user).all()
#     assistants_payload = [{
#         "id": a.id,
#         "vapi_assistant_id": a.vapi_assistant_id,
#         "name": a.name,
#         "provider": a.provider,
#         "model": a.model,
#         "first_message": a.first_message,
#         "systemPrompt": a.systemPrompt,
#         "attached_Number": a.attached_Number,
#         "vapi_phone_uuid": a.vapi_phone_uuid,
#         "draft": a.draft,
#         "assistant_toggle": a.assistant_toggle,
#         "category": a.category,
#         "voice_model": a.voice_model,
#         "languages": a.languages,
#         "created_at": a.created_at,
#         "updated_at": a.updated_at,
#     } for a in assistants]

#     call_logs = await CallLog.filter(user=user).all()
#     call_logs_payload = [{
#         "id": c.id,
#         "lead_id": c.lead_id,
#         "call_started_at": c.call_started_at,
#         "customer_number": c.customer_number,
#         "customer_name": c.customer_name,
#         "call_id": c.call_id,
#         "cost": c.cost,
#         "call_ended_at": c.call_ended_at,
#         "call_ended_reason": c.call_ended_reason,
#         "call_duration": c.call_duration,
#         "is_transferred": c.is_transferred,
#         "status": c.status,
#         "criteria_satisfied": c.criteria_satisfied,
#     } for c in call_logs]

#     docs = await Documents.filter(user=user).all()
#     docs_payload = [{
#         "id": d.id,
#         "file_name": d.file_name,
#         "vapi_file_id": d.vapi_file_id,
#     } for d in docs]

#     leads_payload = []
#     try:
#         from models.file import File
#         user_files = await File.filter(user=user).all()
#         file_ids = [f.id for f in user_files]
#         if file_ids:
#             leads = await Lead.filter(file_id__in=file_ids).all()
#             for l in leads:
#                 leads_payload.append({
#                     "id": l.id,
#                     "first_name": l.first_name,
#                     "last_name": l.last_name,
#                     "email": l.email,
#                     "mobile": l.mobile,
#                     "state": l.state,
#                     "timezone": l.timezone,
#                     "dnc": l.dnc,
#                     "submit_for_approval": l.submit_for_approval,
#                     "other_data": l.other_data,
#                     "add_date": getattr(l, "add_date", None),
#                 })
#     except Exception as e:
#         print(f"Note: collecting leads for user {user.id} raised: {str(e)}")

#     return {
#         "user": {
#             "id": user.id,
#             "name": user.name,
#             "email": user.email,
#             "email_verified": user.email_verified,
#             "role": getattr(user, "role", "user"),
#             "profile_photo": getattr(user, "profile_photo", None),
#             "profile_photo_url": _profile_photo_url_for_user(user.id, getattr(user, "profile_photo", None)),
#         },
#         "counts": {
#             "purchased_numbers": len(numbers_payload),
#             "assistants": len(assistants_payload),
#             "call_logs": len(call_logs_payload),
#             "documents": len(docs_payload),
#             "leads": len(leads_payload),
#         },
#         "purchased_numbers": numbers_payload,
#         "assistants": assistants_payload,
#         "call_logs": call_logs_payload,
#         "documents": docs_payload,
#         "leads": leads_payload,
#     }

# @admin_router.get("/users/{user_id}/details")
# async def get_user_details(user_id: int, current_user: User = Depends(admin_required)):
#     user = await User.get_or_none(id=user_id)
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")
#     details = await _collect_user_details(user)
#     return {"success": True, "details": details}

# @admin_router.get("/users/details")
# async def get_all_users_details(current_user: User = Depends(admin_required)):
#     users = await User.all()
#     details_list = []
#     for u in users:
#         details_list.append(await _collect_user_details(u))
#     return {"success": True, "total_users": len(details_list), "users": details_list}

# @admin_router.get("/basic-admin-stats")
# async def basic_admin_stats(current_user: User = Depends(admin_required)):
#     try:
#         from datetime import datetime, timezone

#         users = await User.all()
#         total_users = len(users)
#         users_by_role: dict[str, int] = {}
#         for u in users:
#             role = getattr(u, "role", "user") or "user"
#             users_by_role[role] = users_by_role.get(role, 0) + 1

#         total_leads = await Lead.all().count()
#         total_assistants = await Assistant.all().count()
#         total_phone_numbers = await PurchasedNumber.all().count()
#         total_kb_docs = await Documents.all().count()
#         total_call_logs = await CallLog.all().count()

#         total_files = 0
#         try:
#             from models.file import File
#             total_files = await File.all().count()
#         except Exception as e:
#             print(f"Note: File model not available or count failed: {str(e)}")

#         numbers_attached = await PurchasedNumber.filter(attached_assistant__isnull=False).count()
#         numbers_unattached = total_phone_numbers - numbers_attached

#         transferred_calls = await CallLog.filter(is_transferred=True).count()
#         not_transferred_calls = total_call_logs - transferred_calls

#         call_logs_by_status: dict[str, int] = {}
#         try:
#             logs = await CallLog.all()
#             for cl in logs:
#                 key = (cl.status or "unknown").lower()
#                 call_logs_by_status[key] = call_logs_by_status.get(key, 0) + 1
#         except Exception as e:
#             print(f"Note: building call_logs_by_status failed: {str(e)}")

#         return {
#             "success": True,
#             "generated_at": datetime.now(timezone.utc).isoformat(),
#             "stats": {
#                 "totals": {
#                     "users": total_users,
#                     "leads": total_leads,
#                     "files": total_files,
#                     "knowledge_base_documents": total_kb_docs,
#                     "assistants": total_assistants,
#                     "phone_numbers": total_phone_numbers,
#                     "call_logs": total_call_logs,
#                 },
#                 "users_by_role": users_by_role,
#                 "phone_numbers": {
#                     "attached_to_assistant": numbers_attached,
#                     "unattached": numbers_unattached,
#                 },
#                 "call_logs": {
#                     "transferred": transferred_calls,
#                     "not_transferred": not_transferred_calls,
#                     "by_status": call_logs_by_status,
#                 },
#             },
#             "message": "Successfully fetched basic admin stats",
#         }

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error fetching admin stats: {str(e)}")

# # ───────────────────────────────────────────────────────────────────────────────
# # Admin-create / bulk-create / reset-password
# # ───────────────────────────────────────────────────────────────────────────────

# @admin_router.post("/users", status_code=201)
# async def admin_create_user(
#     payload: AdminCreateUserRequest,
#     current_user: User = Depends(admin_required),
# ):
#     try:
#         valid_roles = ["user", "admin"]
#         if payload.role not in valid_roles:
#             raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}")

#         existing = await User.filter(email=payload.email).first()
#         if existing:
#             raise HTTPException(status_code=400, detail="Email is already taken by another user")

#         raw_password = payload.password or _gen_password(12)
#         hashed = _hash_password(raw_password)

#         user = await User.create(
#             name=payload.name,
#             email=payload.email,
#             password=hashed,
#             role=payload.role,
#             email_verified=True,   # ✅ always verified when created by admin
#             profile_photo=None,
#         )

#         return {
#             "success": True,
#             "detail": "User created successfully.",
#             "created_user": {
#                 "id": user.id,
#                 "name": user.name,
#                 "email": user.email,
#                 "email_verified": user.email_verified,
#                 "role": user.role,
#                 "profile_photo": getattr(user, "profile_photo", None),
#                 "profile_photo_url": _profile_photo_url_for_user(user.id, getattr(user, "profile_photo", None)),
#             },
#             "initial_password": None if payload.password else raw_password,  # share securely
#         }
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error creating user: {str(e)}")

# @admin_router.post("/users/bulk", status_code=201)
# async def admin_bulk_create_users(
#     payload: AdminBulkCreateUsersRequest,
#     current_user: User = Depends(admin_required),
# ):
#     results = {"created": [], "errors": []}
#     valid_roles = ["user", "admin"]

#     for idx, item in enumerate(payload.users, start=1):
#         try:
#             if item.role not in valid_roles:
#                 raise HTTPException(status_code=400, detail=f"Invalid role '{item.role}'")

#             exists = await User.filter(email=item.email).first()
#             if exists:
#                 results["errors"].append({"index": idx, "email": item.email, "error": "Email already exists"})
#                 continue

#             raw_password = item.password or _gen_password(12)
#             hashed = _hash_password(raw_password)

#             user = await User.create(
#                 name=item.name,
#                 email=item.email,
#                 password=hashed,
#                 role=item.role,
#                 email_verified=True,  # ✅ always verified
#                 profile_photo=None,
#             )

#             results["created"].append({
#                 "id": user.id,
#                 "name": user.name,
#                 "email": user.email,
#                 "role": user.role,
#                 "email_verified": user.email_verified,
#                 "initial_password": None if item.password else raw_password,  # share securely
#                 "profile_photo_url": _profile_photo_url_for_user(user.id, getattr(user, "profile_photo", None)),
#             })
#         except HTTPException as he:
#             results["errors"].append({"index": idx, "email": item.email, "error": he.detail})
#         except Exception as e:
#             results["errors"].append({"index": idx, "email": item.email, "error": str(e)})

#     return {
#         "success": True,
#         "summary": {
#             "requested": len(payload.users),
#             "created": len(results["created"]),
#             "failed": len(results["errors"]),
#         },
#         "results": results,
#     }

# @admin_router.post("/users/{user_id}/reset-password")
# async def admin_reset_user_password(
#     user_id: int,
#     body: AdminResetPasswordRequest,
#     current_user: User = Depends(admin_required),
# ):
#     try:
#         user = await User.get_or_none(id=user_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         new_plain = body.new_password or _gen_password(12)
#         user.password = _hash_password(new_plain)
#         await user.save()

#         return {
#             "success": True,
#             "detail": f"Password reset for user {user_id}.",
#             "new_password": None if body.new_password else new_plain,  # only return if auto-generated
#         }
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error resetting password: {str(e)}")







# third update



from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr
from models.auth import User  # Code is not used for admin-created users
from models.purchased_numbers import PurchasedNumber
from models.assistant import Assistant
from models.lead import Lead
from models.call_log import CallLog
from models.documents import Documents
from helpers.token_helper import admin_required
from helpers.vapi_helper import get_headers
from datetime import datetime, timedelta
from argon2 import PasswordHasher  # <-- match auth controller
import secrets
import string
import os
import httpx
from dotenv import load_dotenv
import requests
import pathlib
import imghdr

load_dotenv()

admin_router = APIRouter()

# ───────────────────────────────────────────────────────────────────────────────
# Profile-photo helpers (FS + DB via user.profile_photo)
# Target folder: media/profile_photos
# Public base URL: /media/profile_photos
# ───────────────────────────────────────────────────────────────────────────────

ALLOWED_EXTS = [".jpg", ".jpeg", ".png", ".webp"]
ALLOWED_MIME_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
MAX_PROFILE_PHOTO_BYTES = 5 * 1024 * 1024  # 5MB

def _profile_dir() -> pathlib.Path:
    p = pathlib.Path(os.environ.get("PROFILE_PHOTOS_DIR", "media/profile_photos"))
    p.mkdir(parents=True, exist_ok=True)
    return p

def _profile_base_url() -> str:
    val = os.environ.get("PROFILE_PHOTOS_BASE_URL", "/media/profile_photos")
    return val.rstrip("/")

def _url_for_filename(name: str | None) -> str | None:
    if not name:
        return None
    return f"{_profile_base_url()}/{name}"

def _existing_profile_photo_path(user_id: int) -> pathlib.Path | None:
    base = _profile_dir()
    for ext in [".jpg", ".jpeg", ".png", ".webp"]:
        candidate = base / f"user_{user_id}{ext}"
        if candidate.exists():
            return candidate
    return None

def _guess_ext(filename: str, content_type: str | None, data: bytes) -> str:
    if content_type in ALLOWED_MIME_TO_EXT:
        return ALLOWED_MIME_TO_EXT[content_type]
    ext = pathlib.Path(filename or "").suffix.lower()
    if ext in ALLOWED_EXTS:
        return ".jpg" if ext == ".jpeg" else ext
    kind = imghdr.what(None, h=data)
    if kind == "jpeg":
        return ".jpg"
    if kind in ("png", "webp"):
        return f".{kind}"
    raise HTTPException(status_code=400, detail="Unsupported image type. Use JPG/PNG/WebP.")

def _profile_photo_url_for_user(user_id: int, db_value: str | None) -> str | None:
    if db_value:
        if db_value.startswith("/") or db_value.startswith("http"):
            return db_value
        try:
            name = pathlib.Path(db_value).name
            if name:
                return _url_for_filename(name)
        except Exception:
            pass
    p = _existing_profile_photo_path(user_id)
    return _url_for_filename(p.name) if p else None

# ───────────────────────────────────────────────────────────────────────────────
# Password helpers (Argon2 to match auth controller)
# ───────────────────────────────────────────────────────────────────────────────

ph = PasswordHasher()

def _hash_password(plain: str) -> str:
    return ph.hash(plain)

def _gen_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))

# ───────────────────────────────────────────────────────────────────────────────
# Schemas
# ───────────────────────────────────────────────────────────────────────────────

class AdminCreateUserRequest(BaseModel):
    name: str
    email: EmailStr
    role: str = "user"          # "user" | "admin"
    password: str | None = None # optional; auto-generated if not provided

class AdminBulkCreateUsersRequest(BaseModel):
    users: list[AdminCreateUserRequest]

class AdminResetPasswordRequest(BaseModel):
    new_password: str | None = None  # if omitted, auto-generate

class UserUpdateRequest(BaseModel):
    name: str
    email: str
    role: str

# ───────────────────────────────────────────────────────────────────────────────
# Users
# ───────────────────────────────────────────────────────────────────────────────

@admin_router.get("/users")
async def get_all_users(current_user: User = Depends(admin_required)):
    try:
        users = await User.all()
        user_list = []
        for user in users:
            user_list.append({
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "email_verified": user.email_verified,
                "role": getattr(user, "role", "user"),
                "profile_photo": getattr(user, "profile_photo", None),
                "profile_photo_url": _profile_photo_url_for_user(user.id, getattr(user, "profile_photo", None)),
            })
        return {
            "success": True,
            "total_users": len(user_list),
            "users": user_list,
            "message": f"Successfully fetched {len(user_list)} users"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching users: {str(e)}")

@admin_router.put("/users/{user_id}")
async def update_user(user_id: int, user_data: UserUpdateRequest, current_user: User = Depends(admin_required)):
    try:
        name = user_data.name
        email = user_data.email
        role = user_data.role

        valid_roles = ["user", "admin"]
        if role not in valid_roles:
            raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}")

        user = await User.get_or_none(id=user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        existing_user = await User.filter(email=email).exclude(id=user_id).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email is already taken by another user")

        user.name = name
        user.email = email
        user.role = role
        await user.save()

        return {
            "success": True,
            "detail": f"User with ID {user_id} has been updated successfully.",
            "updated_user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "email_verified": user.email_verified,
                "role": user.role,
                "profile_photo": getattr(user, "profile_photo", None),
                "profile_photo_url": _profile_photo_url_for_user(user.id, getattr(user, "profile_photo", None)),
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating user: {str(e)}")

# Manage delete alias
@admin_router.delete("/manage/user-accounts/{user_id}")
async def manage_delete_user_account(user_id: int, current_user: User = Depends(admin_required)):
    return await delete_user(user_id, current_user)

@admin_router.delete("/users/{user_id}")
async def delete_user(user_id: int, current_user: User = Depends(admin_required)):
    try:
        user = await User.get_or_none(id=user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if user.id == current_user.id:
            raise HTTPException(status_code=400, detail="You cannot delete your own account")

        assistants_count = await Assistant.filter(user=user).count()
        call_logs_count = await CallLog.filter(user=user).count()
        purchased_numbers_count = await PurchasedNumber.filter(user=user).count()

        assistants = await Assistant.filter(user=user).all()
        for assistant in assistants:
            try:
                if assistant.vapi_phone_uuid:
                    requests.patch(
                        f"https://api.vapi.ai/phone-number/{assistant.vapi_phone_uuid}",
                        json={"assistantId": None},
                        headers=get_headers()
                    ).raise_for_status()

                vapi_assistant_id = assistant.vapi_assistant_id
                vapi_url = f"{os.environ.get('VAPI_URL', 'https://api.vapi.ai/assistant')}/{vapi_assistant_id}"
                requests.delete(vapi_url, headers=get_headers())
            except Exception as e:
                print(f"Warning: Failed to delete assistant {assistant.id} from VAPI: {str(e)}")

            await assistant.delete()

        await CallLog.filter(user=user).delete()
        await PurchasedNumber.filter(user=user).delete()

        try:
            from models.file import File
            user_files = await File.filter(user=user).all()
            file_ids = [file.id for file in user_files]
            if file_ids:
                await Lead.filter(file_id__in=file_ids).delete()
            await File.filter(user=user).delete()
        except Exception as e:
            print(f"Warning: Error deleting user files and associated leads: {str(e)}")

        # Profile photo cleanup (FS)
        try:
            p = _existing_profile_photo_path(user.id)
            if p:
                p.unlink(missing_ok=True)
        except Exception as e:
            print(f"Warning: Error deleting profile photo for user {user.id}: {str(e)}")

        await user.delete()

        return {
            "success": True,
            "detail": f"User with ID {user_id} and all related data have been deleted successfully.",
            "deleted_data": {
                "assistants": assistants_count,
                "call_logs": call_logs_count,
                "purchased_numbers": purchased_numbers_count,
                "files_and_leads": "deleted"
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting user: {str(e)}")

# ───────────────────────────────────────────────────────────────────────────────
# Phone Numbers
# ───────────────────────────────────────────────────────────────────────────────

@admin_router.get("/phone-numbers")
async def get_all_phone_numbers(current_user: User = Depends(admin_required)):
    try:
        phone_numbers = await PurchasedNumber.all().prefetch_related('user')
        phone_number_list = []
        for phone_number in phone_numbers:
            phone_number_list.append({
                "id": phone_number.id,
                "phone_number": phone_number.phone_number,
                "friendly_name": phone_number.friendly_name,
                "region": phone_number.region,
                "postal_code": phone_number.postal_code,
                "iso_country": phone_number.iso_country,
                "last_month_payment": phone_number.last_month_payment,
                "created_at": phone_number.created_at,
                "updated_at": phone_number.updated_at,
                "attached_assistant": phone_number.attached_assistant,
                "vapi_phone_uuid": phone_number.vapi_phone_uuid,
                "user": {
                    "id": phone_number.user.id,
                    "name": phone_number.user.name,
                    "email": phone_number.user.email
                } if phone_number.user else None
            })
        return {
            "success": True,
            "total_phone_numbers": len(phone_number_list),
            "phone_numbers": phone_number_list,
            "message": f"Successfully fetched {len(phone_number_list)} phone numbers"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching phone numbers: {str(e)}")

@admin_router.delete("/phone-numbers/{phone_number_id}")
async def delete_phone_number(phone_number_id: int, current_user: User = Depends(admin_required)):
    try:
        phone_number = await PurchasedNumber.get_or_none(id=phone_number_id)
        if not phone_number:
            raise HTTPException(status_code=404, detail="Phone number not found")

        vapi_phone_uuid = phone_number.vapi_phone_uuid
        phone_number_value = phone_number.phone_number

        if phone_number.attached_assistant:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete phone number '{phone_number_value}' as it is currently attached to an assistant. Please detach it first."
            )

        if vapi_phone_uuid:
            try:
                vapi_api_key = os.environ.get("VAPI_API_KEY")
                vapi_org_id = os.environ.get("VAPI_ORG_ID")
                if not vapi_api_key or not vapi_org_id:
                    raise HTTPException(status_code=500, detail="VAPI credentials not configured")

                url = f"https://api.vapi.ai/phone-number/{vapi_phone_uuid}"
                headers = {"Authorization": f"Bearer {vapi_api_key}", "Content-Type": "application/json"}
                async with httpx.AsyncClient() as client:
                    response = await client.delete(url, headers=headers)
                    if response.status_code in [200, 201, 204]:
                        print(f"Successfully deleted phone number {vapi_phone_uuid} from VAPI")
                    else:
                        print(f"Warning: Failed to delete phone number {vapi_phone_uuid} from VAPI. Status: {response.status_code}")
            except Exception as e:
                print(f"Warning: Error deleting phone number {vapi_phone_uuid} from VAPI: {str(e)}")

        await phone_number.delete()

        return {
            "success": True,
            "detail": f"Phone number '{phone_number_value}' has been deleted successfully.",
            "deleted_data": {
                "phone_number_id": phone_number_id,
                "phone_number": phone_number_value,
                "vapi_phone_uuid": vapi_phone_uuid,
                "vapi_deleted": vapi_phone_uuid is not None
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting phone number: {str(e)}")

# ───────────────────────────────────────────────────────────────────────────────
# Assistants
# ───────────────────────────────────────────────────────────────────────────────

@admin_router.get("/assistants")
async def get_all_assistants(current_user: User = Depends(admin_required)):
    try:
        assistants = await Assistant.all().prefetch_related('user')
        assistant_list = []
        for assistant in assistants:
            assistant_list.append({
                "id": assistant.id,
                "vapi_assistant_id": assistant.vapi_assistant_id,
                "name": assistant.name,
                "provider": assistant.provider,
                "first_message": assistant.first_message,
                "model": assistant.model,
                "systemPrompt": assistant.systemPrompt,
                "knowledgeBase": assistant.knowledgeBase,
                "leadsfile": assistant.leadsfile,
                "temperature": assistant.temperature,
                "maxTokens": assistant.maxTokens,
                "transcribe_provider": assistant.transcribe_provider,
                "transcribe_language": assistant.transcribe_language,
                "transcribe_model": assistant.transcribe_model,
                "voice_provider": assistant.voice_provider,
                "voice": assistant.voice,
                "forwardingPhoneNumber": assistant.forwardingPhoneNumber,
                "endCallPhrases": assistant.endCallPhrases,
                "attached_Number": assistant.attached_Number,
                "vapi_phone_uuid": assistant.vapi_phone_uuid,
                "draft": assistant.draft,
                "assistant_toggle": assistant.assistant_toggle,
                "success_evalution": assistant.success_evalution,
                "category": assistant.category,
                "voice_model": assistant.voice_model,
                "languages": assistant.languages,
                "created_at": assistant.created_at,
                "updated_at": assistant.updated_at,
                "speed": assistant.speed,
                "stability": assistant.stability,
                "similarityBoost": assistant.similarityBoost,
                "user": {
                    "id": assistant.user.id,
                    "name": assistant.user.name,
                    "email": assistant.user.email
                } if assistant.user else None
            })
        return {
            "success": True,
            "total_assistants": len(assistant_list),
            "assistants": assistant_list,
            "message": f"Successfully fetched {len(assistant_list)} assistants"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching assistants: {str(e)}")

@admin_router.delete("/assistants/{assistant_id}")
async def delete_assistant(assistant_id: int, current_user: User = Depends(admin_required)):
    try:
        assistant = await Assistant.get_or_none(id=assistant_id)
        if not assistant:
            raise HTTPException(status_code=404, detail="Assistant not found")

        if assistant.vapi_phone_uuid:
            try:
                requests.patch(
                    f"https://api.vapi.ai/phone-number/{assistant.vapi_phone_uuid}",
                    json={"assistantId": None},
                    headers=get_headers()
                ).raise_for_status()
            except Exception as e:
                print(f"Warning: Failed to detach phone number from VAPI: {str(e)}")

        if assistant.attached_Number:
            phone_number = await PurchasedNumber.get_or_none(attached_assistant=assistant_id)
            if phone_number:
                await PurchasedNumber.filter(attached_assistant=assistant_id).update(attached_assistant=None)

        vapi_assistant_id = assistant.vapi_assistant_id
        vapi_url = f"{os.environ.get('VAPI_URL', 'https://api.vapi.ai/assistant')}/{vapi_assistant_id}"

        try:
            response = requests.delete(vapi_url, headers=get_headers())
            if response.status_code in [200, 201, 204]:
                await assistant.delete()
                return {"success": True, "detail": "Assistant deleted from VAPI and local DB."}
            else:
                await assistant.delete()
                return {
                    "success": True,
                    "detail": f"Assistant deleted locally. VAPI deletion failed with status {response.status_code}: {response.text}"
                }
        except Exception as e:
            await assistant.delete()
            return {"success": True, "detail": f"Assistant deleted locally. VAPI deletion failed: {str(e)}"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting assistant: {str(e)}")

# ───────────────────────────────────────────────────────────────────────────────
# Leads
# ───────────────────────────────────────────────────────────────────────────────

@admin_router.get("/leadss")
async def get_all_leads(current_user: User = Depends(admin_required)):
    try:
        leads = await Lead.all()
        lead_list = []
        for lead in leads:
            lead_list.append({
                "id": lead.id,
                "first_name": lead.first_name,
                "last_name": lead.last_name,
                "email": lead.email,
                "add_date": lead.add_date,
                "salesforce_id": lead.salesforce_id,
                "mobile": lead.mobile,
                "state": lead.state,
                "timezone": lead.timezone,
                "dnc": lead.dnc,
                "submit_for_approval": lead.submit_for_approval,
                "other_data": lead.other_data,
                "last_called_at": lead.last_called_at,
                "call_count": lead.call_count,
                "created_at": lead.created_at,
                "updated_at": lead.updated_at
            })
        return {
            "success": True,
            "total_leads": len(lead_list),
            "leads": lead_list,
            "message": f"Successfully fetched {len(lead_list)} leads"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching leads: {str(e)}")

class LeadUpdateRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    add_date: str  # YYYY-MM-DD
    salesforce_id: str | None = None
    mobile: str
    state: str | None = None
    timezone: str | None = None
    dnc: bool = False
    submit_for_approval: bool = False
    other_data: dict | None = None
    call_count: int = 0

@admin_router.put("/leads/{lead_id}")
async def update_lead(lead_id: int, lead_data: LeadUpdateRequest, current_user: User = Depends(admin_required)):
    try:
        from datetime import datetime
        lead = await Lead.get_or_none(id=lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        try:
            add_date = datetime.strptime(lead_data.add_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD format")

        lead.first_name = lead_data.first_name
        lead.last_name = lead_data.last_name
        lead.email = lead_data.email
        lead.add_date = add_date
        lead.salesforce_id = lead_data.salesforce_id
        lead.mobile = lead_data.mobile
        lead.state = lead_data.state
        lead.timezone = lead_data.timezone
        lead.dnc = lead_data.dnc
        lead.submit_for_approval = lead_data.submit_for_approval
        lead.other_data = lead_data.other_data
        lead.call_count = lead_data.call_count
        await lead.save()

        return {
            "success": True,
            "detail": f"Lead with ID {lead_id} has been updated successfully.",
            "updated_lead": {
                "id": lead.id,
                "first_name": lead.first_name,
                "last_name": lead.last_name,
                "email": lead.email,
                "add_date": lead.add_date.isoformat(),
                "salesforce_id": lead.salesforce_id,
                "mobile": lead.mobile,
                "state": lead.state,
                "timezone": lead.timezone,
                "dnc": lead.dnc,
                "submit_for_approval": lead.submit_for_approval,
                "other_data": lead.other_data,
                "last_called_at": lead.last_called_at.isoformat() if lead.last_called_at else None,
                "call_count": lead.call_count,
                "created_at": lead.created_at.isoformat(),
                "updated_at": lead.updated_at.isoformat()
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating lead: {str(e)}")

# ───────────────────────────────────────────────────────────────────────────────
# Call logs
# ───────────────────────────────────────────────────────────────────────────────

@admin_router.get("/call-logs")
async def get_all_call_logs(current_user: User = Depends(admin_required)):
    try:
        call_logs = await CallLog.all().prefetch_related('user')
        call_log_list = []
        for call_log in call_logs:
            call_log_list.append({
                "id": call_log.id,
                "lead_id": call_log.lead_id,
                "call_started_at": call_log.call_started_at,
                "customer_number": call_log.customer_number,
                "customer_name": call_log.customer_name,
                "call_id": call_log.call_id,
                "cost": call_log.cost,
                "call_ended_at": call_log.call_ended_at,
                "call_ended_reason": call_log.call_ended_reason,
                "call_duration": call_log.call_duration,
                "is_transferred": call_log.is_transferred,
                "status": call_log.status,
                "criteria_satisfied": call_log.criteria_satisfied,
                "user": {
                    "id": call_log.user.id,
                    "name": call_log.user.name,
                    "email": call_log.user.email
                } if call_log.user else None
            })
        return {
            "success": True,
            "total_call_logs": len(call_log_list),
            "call_logs": call_log_list,
            "message": f"Successfully fetched {len(call_log_list)} call logs"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching call logs: {str(e)}")

@admin_router.get("/vapi-call-logs")
async def get_vapi_call_logs(current_user: User = Depends(admin_required)):
    try:
        vapi_api_key = os.environ.get("VAPI_API_KEY")
        vapi_org_id = os.environ.get("VAPI_ORG_ID")
        if not vapi_api_key or not vapi_org_id:
            raise HTTPException(status_code=500, detail="VAPI credentials not configured")

        url = "https://api.vapi.ai/call/"
        headers = {"Authorization": f"Bearer {vapi_api_key}", "Content-Type": "application/json"}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                vapi_data = response.json()
                call_logs = vapi_data if isinstance(vapi_data, list) else []
                call_log_list = []
                for call_log in call_logs:
                    call_log_list.append({
                        "id": call_log.get("id"),
                        "assistant_id": call_log.get("assistantId"),
                        "phone_number_id": call_log.get("phoneNumberId"),
                        "status": call_log.get("status"),
                        "started_at": call_log.get("startedAt"),
                        "ended_at": call_log.get("endedAt"),
                        "duration": call_log.get("duration"),
                        "cost": call_log.get("cost"),
                        "customer_number": call_log.get("customerNumber"),
                        "customer_name": call_log.get("customerName"),
                        "call_id": call_log.get("callId"),
                        "ended_reason": call_log.get("endedReason"),
                        "is_transferred": call_log.get("isTransferred"),
                        "criteria_satisfied": call_log.get("criteriaSatisfied"),
                        "summary": call_log.get("summary"),
                        "transcript": call_log.get("transcript"),
                        "analysis": call_log.get("analysis"),
                        "recording_url": call_log.get("recordingUrl"),
                        "created_at": call_log.get("createdAt"),
                        "updated_at": call_log.get("UpdatedAt") or call_log.get("updatedAt")
                    })
                return {
                    "success": True,
                    "total_call_logs": len(call_log_list),
                    "call_logs": call_log_list,
                    "message": f"Successfully fetched {len(call_log_list)} call logs from VAPI"
                }
            else:
                raise HTTPException(status_code=response.status_code, detail=f"Error fetching call logs from VAPI: {response.text}")

    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Network error while fetching call logs from VAPI: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching call logs from VAPI: {str(e)}")

@admin_router.delete("/call-logs/{call_log_id}")
async def delete_call_log(call_log_id: int, current_user: User = Depends(admin_required)):
    try:
        call_log = await CallLog.get_or_none(id=call_log_id)
        if not call_log:
            raise HTTPException(status_code=404, detail="Call log not found")

        call_id = call_log.call_id
        customer_name = call_log.customer_name
        customer_number = call_log.customer_number

        if call_id:
            try:
                vapi_api_key = os.environ.get("VAPI_API_KEY")
                vapi_org_id = os.environ.get("VAPI_ORG_ID")
                if not vapi_api_key or not vapi_org_id:
                    raise HTTPException(status_code=500, detail="VAPI credentials not configured")

                url = f"https://api.vapi.ai/call/{call_id}"
                headers = {"Authorization": f"Bearer {vapi_api_key}", "Content-Type": "application/json"}
                async with httpx.AsyncClient() as client:
                    response = await client.delete(url, headers=headers)
                    if response.status_code in [200, 201, 204]:
                        print(f"Successfully deleted call {call_id} from VAPI")
                    else:
                        print(f"Warning: Failed to delete call {call_id} from VAPI. Status: {response.status_code}")
            except Exception as e:
                print(f"Warning: Error deleting call {call_id} from VAPI: {str(e)}")

        await call_log.delete()

        return {
            "success": True,
            "detail": f"Call log for '{customer_name}' ({customer_number}) has been deleted successfully.",
            "deleted_data": {
                "call_log_id": call_log_id,
                "call_id": call_id,
                "customer_name": customer_name,
                "customer_number": customer_number,
                "vapi_deleted": call_id is not None
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting call log: {str(e)}")

# ───────────────────────────────────────────────────────────────────────────────
# Knowledge Base
# ───────────────────────────────────────────────────────────────────────────────

@admin_router.get("/knowledge-base")
async def get_all_knowledge_base(current_user: User = Depends(admin_required)):
    try:
        documents = await Documents.all().prefetch_related('user')
        knowledge_base_list = []
        for document in documents:
            knowledge_base_list.append({
                "id": document.id,
                "file_name": document.file_name,
                "vapi_file_id": document.vapi_file_id,
                "user": {
                    "id": document.user.id,
                    "name": document.user.name,
                    "email": document.user.email
                } if document.user else None
            })
        return {
            "success": True,
            "total_knowledge_base": len(knowledge_base_list),
            "knowledge_base": knowledge_base_list,
            "message": f"Successfully fetched {len(knowledge_base_list)} knowledge base documents"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching knowledge base: {str(e)}")

@admin_router.get("/knowledge-base/file/{vapi_file_id}")
async def get_vapi_file_details(vapi_file_id: str, current_user: User = Depends(admin_required)):
    try:
        vapi_api_key = os.environ.get("VAPI_API_KEY")
        vapi_org_id = os.environ.get("VAPI_ORG_ID")
        if not vapi_api_key or not vapi_org_id:
            raise HTTPException(status_code=500, detail="VAPI credentials not configured")

        url = f"https://api.vapi.ai/file/{vapi_file_id}"
        headers = {"Authorization": f"Bearer {vapi_api_key}", "Content-Type": "application/json"}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                vapi_data = response.json()
                file_data = {
                    "id": vapi_data.get("id"),
                    "name": vapi_data.get("name"),
                    "size": vapi_data.get("size"),
                    "type": vapi_data.get("type"),
                    "status": vapi_data.get("status"),
                    "created_at": vapi_data.get("createdAt"),
                    "updated_at": vapi_data.get("updatedAt"),
                    "url": vapi_data.get("url"),
                    "metadata": vapi_data.get("metadata", {}),
                    "processing_status": vapi_data.get("processingStatus"),
                    "file_type": vapi_data.get("fileType"),
                    "mime_type": vapi_data.get("mimeType"),
                    "file_size_bytes": vapi_data.get("fileSizeBytes"),
                    "processing_error": vapi_data.get("processingError"),
                    "is_processed": vapi_data.get("isProcessed", False)
                }
                return {"success": True, "file_details": file_data, "message": f"Successfully fetched file details for {vapi_file_id}"}
            else:
                raise HTTPException(status_code=response.status_code, detail=f"Error fetching file details from VAPI: {response.text}")

    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Network error while fetching file details from VAPI: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching file details from VAPI: {str(e)}")

@admin_router.delete("/knowledge-base/{document_id}")
async def delete_knowledge_base_file(document_id: int, current_user: User = Depends(admin_required)):
    try:
        document = await Documents.get_or_none(id=document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Knowledge base file not found")

        vapi_file_id = document.vapi_file_id
        file_name = document.file_name

        if vapi_file_id:
            try:
                vapi_api_key = os.environ.get("VAPI_API_KEY")
                vapi_org_id = os.environ.get("VAPI_ORG_ID")
                if not vapi_api_key or not vapi_org_id:
                    raise HTTPException(status_code=500, detail="VAPI credentials not configured")

                url = f"https://api.vapi.ai/file/{vapi_file_id}"
                headers = {"Authorization": f"Bearer {vapi_api_key}", "Content-Type": "application/json"}
                async with httpx.AsyncClient() as client:
                    response = await client.delete(url, headers=headers)
                    if response.status_code in [200, 201, 204]:
                        print(f"Successfully deleted file {vapi_file_id} from VAPI")
                    else:
                        print(f"Warning: Failed to delete file {vapi_file_id} from VAPI. Status: {response.status_code}")
            except Exception as e:
                print(f"Warning: Error deleting file {vapi_file_id} from VAPI: {str(e)}")

        await document.delete()

        return {
            "success": True,
            "detail": f"Knowledge base file '{file_name}' has been deleted successfully.",
            "deleted_data": {
                "document_id": document_id,
                "file_name": file_name,
                "vapi_file_id": vapi_file_id,
                "vapi_deleted": vapi_file_id is not None
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting knowledge base file: {str(e)}")

# ───────────────────────────────────────────────────────────────────────────────
# Profile photo (self + admin)
# ───────────────────────────────────────────────────────────────────────────────

@admin_router.put("/me/profile-photo")
async def upload_or_update_my_profile_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(admin_required),
):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")
    if len(data) > MAX_PROFILE_PHOTO_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 5MB).")

    ext = _guess_ext(file.filename, file.content_type, data)
    dst_dir = _profile_dir()

    old = _existing_profile_photo_path(current_user.id)
    if old and old.suffix.lower() != ext:
        try:
            old.unlink(missing_ok=True)
        except Exception:
            pass

    dst = dst_dir / f"user_{current_user.id}{ext}"
    try:
        with open(dst, "wb") as f:
            f.write(data)
    finally:
        await file.close()

    photo_url = _url_for_filename(dst.name)
    current_user.profile_photo = photo_url
    await current_user.save()

    return {
        "success": True,
        "detail": "Profile photo uploaded.",
        "file_name": dst.name,
        "file_path": str(dst),
        "profile_photo": photo_url,
        "profile_photo_url": photo_url,
    }

@admin_router.get("/me/profile-photo")
async def get_my_profile_photo(current_user: User = Depends(admin_required)):
    p = _existing_profile_photo_path(current_user.id)
    url = _profile_photo_url_for_user(current_user.id, current_user.profile_photo)
    return {
        "success": True,
        "exists": (p is not None) or bool(url),
        "db_value": current_user.profile_photo,
        "file_name": p.name if p else (pathlib.Path(current_user.profile_photo).name if (current_user.profile_photo and not current_user.profile_photo.startswith("/")) else None),
        "file_path": str(p) if p else None,
        "profile_photo_url": url,
    }

@admin_router.get("/me/profile-photo/raw")
async def get_my_profile_photo_raw(current_user: User = Depends(admin_required)):
    p = _existing_profile_photo_path(current_user.id)
    if p and p.exists():
        mt = "image/jpeg" if p.suffix.lower() in [".jpg", ".jpeg"] else "image/png" if p.suffix.lower() == ".png" else "image/webp"
        return Response(content=p.read_bytes(), media_type=mt)
    raise HTTPException(status_code=404, detail="Profile photo not found.")

@admin_router.delete("/me/profile-photo")
async def delete_my_profile_photo(current_user: User = Depends(admin_required)):
    p = _existing_profile_photo_path(current_user.id)
    if p:
        try:
            p.unlink(missing_ok=True)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete photo: {str(e)}")

    current_user.profile_photo = None
    await current_user.save()
    return {"success": True, "detail": "Profile photo deleted."}

@admin_router.get("/users/{user_id}/profile-photo")
async def admin_get_user_profile_photo(user_id: int, current_user: User = Depends(admin_required)):
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    p = _existing_profile_photo_path(user_id)
    url = _profile_photo_url_for_user(user_id, user.profile_photo)
    return {
        "success": True,
        "exists": (p is not None) or bool(url),
        "db_value": user.profile_photo,
        "file_name": p.name if p else (pathlib.Path(user.profile_photo).name if (user.profile_photo and not user.profile_photo.startswith("/")) else None),
        "file_path": str(p) if p else None,
        "profile_photo_url": url,
    }

@admin_router.get("/users/{user_id}/profile-photo/raw")
async def admin_get_user_profile_photo_raw(user_id: int, current_user: User = Depends(admin_required)):
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    p = _existing_profile_photo_path(user_id)
    if p and p.exists():
        mt = "image/jpeg" if p.suffix.lower() in [".jpg", ".jpeg"] else "image/png" if p.suffix.lower() == ".png" else "image/webp"
        return Response(content=p.read_bytes(), media_type=mt)
    raise HTTPException(status_code=404, detail="Profile photo not found.")

@admin_router.delete("/users/{user_id}/profile-photo")
async def admin_delete_user_profile_photo(user_id: int, current_user: User = Depends(admin_required)):
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    p = _existing_profile_photo_path(user_id)
    if p:
        try:
            p.unlink(missing_ok=True)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete photo: {str(e)}")
    user.profile_photo = None
    await user.save()
    return {"success": True, "detail": f"Deleted profile photo for user {user_id}."}

# ───────────────────────────────────────────────────────────────────────────────
# “Main” user-details endpoints (deep export)
# ───────────────────────────────────────────────────────────────────────────────

async def _collect_user_details(user: User) -> dict:
    numbers = await PurchasedNumber.filter(user=user).all()
    numbers_payload = [{
        "id": n.id,
        "phone_number": n.phone_number,
        "friendly_name": n.friendly_name,
        "region": n.region,
        "postal_code": n.postal_code,
        "iso_country": n.iso_country,
        "last_month_payment": n.last_month_payment,
        "attached_assistant": n.attached_assistant,
        "vapi_phone_uuid": n.vapi_phone_uuid,
        "created_at": n.created_at,
        "updated_at": n.updated_at,
    } for n in numbers]

    assistants = await Assistant.filter(user=user).all()
    assistants_payload = [{
        "id": a.id,
        "vapi_assistant_id": a.vapi_assistant_id,
        "name": a.name,
        "provider": a.provider,
        "model": a.model,
        "first_message": a.first_message,
        "systemPrompt": a.systemPrompt,
        "attached_Number": a.attached_Number,
        "vapi_phone_uuid": a.vapi_phone_uuid,
        "draft": a.draft,
        "assistant_toggle": a.assistant_toggle,
        "category": a.category,
        "voice_model": a.voice_model,
        "languages": a.languages,
        "created_at": a.created_at,
        "updated_at": a.updated_at,
    } for a in assistants]

    call_logs = await CallLog.filter(user=user).all()
    call_logs_payload = [{
        "id": c.id,
        "lead_id": c.lead_id,
        "call_started_at": c.call_started_at,
        "customer_number": c.customer_number,
        "customer_name": c.customer_name,
        "call_id": c.call_id,
        "cost": c.cost,
        "call_ended_at": c.call_ended_at,
        "call_ended_reason": c.call_ended_reason,
        "call_duration": c.call_duration,
        "is_transferred": c.is_transferred,
        "status": c.status,
        "criteria_satisfied": c.criteria_satisfied,
    } for c in call_logs]

    docs = await Documents.filter(user=user).all()
    docs_payload = [{
        "id": d.id,
        "file_name": d.file_name,
        "vapi_file_id": d.vapi_file_id,
    } for d in docs]

    leads_payload = []
    try:
        from models.file import File
        user_files = await File.filter(user=user).all()
        file_ids = [f.id for f in user_files]
        if file_ids:
            leads = await Lead.filter(file_id__in=file_ids).all()
            for l in leads:
                leads_payload.append({
                    "id": l.id,
                    "first_name": l.first_name,
                    "last_name": l.last_name,
                    "email": l.email,
                    "mobile": l.mobile,
                    "state": l.state,
                    "timezone": l.timezone,
                    "dnc": l.dnc,
                    "submit_for_approval": l.submit_for_approval,
                    "other_data": l.other_data,
                    "add_date": getattr(l, "add_date", None),
                })
    except Exception as e:
        print(f"Note: collecting leads for user {user.id} raised: {str(e)}")

    return {
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "email_verified": user.email_verified,
            "role": getattr(user, "role", "user"),
            "profile_photo": getattr(user, "profile_photo", None),
            "profile_photo_url": _profile_photo_url_for_user(user.id, getattr(user, "profile_photo", None)),
        },
        "counts": {
            "purchased_numbers": len(numbers_payload),
            "assistants": len(assistants_payload),
            "call_logs": len(call_logs_payload),
            "documents": len(docs_payload),
            "leads": len(leads_payload),
        },
        "purchased_numbers": numbers_payload,
        "assistants": assistants_payload,
        "call_logs": call_logs_payload,
        "documents": docs_payload,
        "leads": leads_payload,
    }

@admin_router.get("/users/{user_id}/details")
async def get_user_details(user_id: int, current_user: User = Depends(admin_required)):
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    details = await _collect_user_details(user)
    return {"success": True, "details": details}

@admin_router.get("/users/details")
async def get_all_users_details(current_user: User = Depends(admin_required)):
    users = await User.all()
    details_list = []
    for u in users:
        details_list.append(await _collect_user_details(u))
    return {"success": True, "total_users": len(details_list), "users": details_list}

@admin_router.get("/basic-admin-stats")
async def basic_admin_stats(current_user: User = Depends(admin_required)):
    try:
        from datetime import datetime, timezone

        users = await User.all()
        total_users = len(users)
        users_by_role: dict[str, int] = {}
        for u in users:
            role = getattr(u, "role", "user") or "user"
            users_by_role[role] = users_by_role.get(role, 0) + 1

        total_leads = await Lead.all().count()
        total_assistants = await Assistant.all().count()
        total_phone_numbers = await PurchasedNumber.all().count()
        total_kb_docs = await Documents.all().count()
        total_call_logs = await CallLog.all().count()

        total_files = 0
        try:
            from models.file import File
            total_files = await File.all().count()
        except Exception as e:
            print(f"Note: File model not available or count failed: {str(e)}")

        numbers_attached = await PurchasedNumber.filter(attached_assistant__isnull=False).count()
        numbers_unattached = total_phone_numbers - numbers_attached

        transferred_calls = await CallLog.filter(is_transferred=True).count()
        not_transferred_calls = total_call_logs - transferred_calls

        call_logs_by_status: dict[str, int] = {}
        try:
            logs = await CallLog.all()
            for cl in logs:
                key = (cl.status or "unknown").lower()
                call_logs_by_status[key] = call_logs_by_status.get(key, 0) + 1
        except Exception as e:
            print(f"Note: building call_logs_by_status failed: {str(e)}")

        return {
            "success": True,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stats": {
                "totals": {
                    "users": total_users,
                    "leads": total_leads,
                    "files": total_files,
                    "knowledge_base_documents": total_kb_docs,
                    "assistants": total_assistants,
                    "phone_numbers": total_phone_numbers,
                    "call_logs": total_call_logs,
                },
                "users_by_role": users_by_role,
                "phone_numbers": {
                    "attached_to_assistant": numbers_attached,
                    "unattached": numbers_unattached,
                },
                "call_logs": {
                    "transferred": transferred_calls,
                    "not_transferred": not_transferred_calls,
                    "by_status": call_logs_by_status,
                },
            },
            "message": "Successfully fetched basic admin stats",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching admin stats: {str(e)}")

# ───────────────────────────────────────────────────────────────────────────────
# Admin-create / bulk-create / reset-password
# ───────────────────────────────────────────────────────────────────────────────

@admin_router.post("/users", status_code=201)
async def admin_create_user(
    payload: AdminCreateUserRequest,
    current_user: User = Depends(admin_required),
):
    try:
        valid_roles = ["user", "admin"]
        if payload.role not in valid_roles:
            raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}")

        existing = await User.filter(email=payload.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email is already taken by another user")

        raw_password = payload.password or _gen_password(12)
        hashed = _hash_password(raw_password)

        user = await User.create(
            name=payload.name,
            email=payload.email,
            password=hashed,
            role=payload.role,
            email_verified=True,   # ✅ always verified when created by admin
            profile_photo=None,
        )

        return {
            "success": True,
            "detail": "User created successfully.",
            "created_user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "email_verified": user.email_verified,
                "role": user.role,
                "profile_photo": getattr(user, "profile_photo", None),
                "profile_photo_url": _profile_photo_url_for_user(user.id, getattr(user, "profile_photo", None)),
            },
            "initial_password": None if payload.password else raw_password,  # share securely
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating user: {str(e)}")

@admin_router.post("/users/bulk", status_code=201)
async def admin_bulk_create_users(
    payload: AdminBulkCreateUsersRequest,
    current_user: User = Depends(admin_required),
):
    results = {"created": [], "errors": []}
    valid_roles = ["user", "admin"]

    for idx, item in enumerate(payload.users, start=1):
        try:
            if item.role not in valid_roles:
                raise HTTPException(status_code=400, detail=f"Invalid role '{item.role}'")

            exists = await User.filter(email=item.email).first()
            if exists:
                results["errors"].append({"index": idx, "email": item.email, "error": "Email already exists"})
                continue

            raw_password = item.password or _gen_password(12)
            hashed = _hash_password(raw_password)

            user = await User.create(
                name=item.name,
                email=item.email,
                password=hashed,
                role=item.role,
                email_verified=True,  # ✅ always verified
                profile_photo=None,
            )

            results["created"].append({
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "role": user.role,
                "email_verified": user.email_verified,
                "initial_password": None if item.password else raw_password,  # share securely
                "profile_photo_url": _profile_photo_url_for_user(user.id, getattr(user, "profile_photo", None)),
            })
        except HTTPException as he:
            results["errors"].append({"index": idx, "email": item.email, "error": he.detail})
        except Exception as e:
            results["errors"].append({"index": idx, "email": item.email, "error": str(e)})

    return {
        "success": True,
        "summary": {
            "requested": len(payload.users),
            "created": len(results["created"]),
            "failed": len(results["errors"]),
        },
        "results": results,
    }

@admin_router.post("/users/{user_id}/reset-password")
async def admin_reset_user_password(
    user_id: int,
    body: AdminResetPasswordRequest,
    current_user: User = Depends(admin_required),
):
    try:
        user = await User.get_or_none(id=user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        new_plain = body.new_password or _gen_password(12)
        user.password = _hash_password(new_plain)
        await user.save()

        return {
            "success": True,
            "detail": f"Password reset for user {user_id}.",
            "new_password": None if body.new_password else new_plain,  # only return if auto-generated
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error resetting password: {str(e)}")
