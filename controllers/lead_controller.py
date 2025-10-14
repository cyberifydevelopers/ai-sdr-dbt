
# from urllib.parse import urlparse
# from fastapi import APIRouter, Form, UploadFile, File as FastAPIFile, HTTPException, Depends, Request
# # from helpers.criteria_check import has_payment_method
# from controllers.crm_controller import _ensure_fresh_token, _get_active_account
# from helpers.get_admin import get_admin
# from helpers.get_user_admin import get_user_admin
# from helpers.import_leads_csv import import_leads_csv, humanize_results
# from helpers.state import stateandtimezone
# from models.lead import Lead
# # from models.logs import Logs
# from models.auth import User
# from models.file import File as FileModel
# from models.crm import IntegrationAccount  # <-- NEW: to read connected CRM tokens
# from pydantic import BaseModel
# from typing import List, Annotated, Optional, Dict, Set
# from httpx import AsyncClient
# from helpers.token_helper import get_current_user
# import asyncio
# # from config import scheduler_status
# from datetime import datetime, timedelta
# # from models.dnc_api_key import DNCAPIkey
# from pydantic import EmailStr, StringConstraints, validator
# from typing_extensions import Annotated
# from controllers.campaign_controller import trigger_campaign_refresh_for_file

# router = APIRouter()


# HUBSPOT_CONTACT_PROPS = "firstname,lastname,email,phone,company,hs_object_id,createdate,lastmodifieddate"

# class DeleteLeadPayload(BaseModel):
#     ids: List[int]

# class StateUpdateRequest(BaseModel):
#     state: str

# class CreateLeadPayload(BaseModel):
#     first_name: str
#     last_name: str
#     email: str
#     add_date: str
#     mobile: str
#     file_id: Optional[int]
#     salesforce_id: str
#     other_data: Optional[Dict[str, str]] = None

# class CreateFilePayload(BaseModel):
#     name: str

# class UpdateLeadPayload(BaseModel):
#     first_name: Optional[str] = None
#     last_name: Optional[str] = None
#     email: Optional[EmailStr] = None
#     mobile: Optional[str] = None
#     salesforce_id: Optional[str] = None
#     add_date: Optional[str] = None
#     file_id: Optional[int] = None
#     # NOTE: allow arbitrary keys (CRM field names)
#     other_data: Optional[Dict[str, str]] = None

# class LeadInput(BaseModel):
#     api_key: str
#     first_name: str
#     last_name: str
#     email: EmailStr
#     mobile: Annotated[str, StringConstraints(min_length=10, max_length=10, pattern=r'^\d{10}$')]
#     file_id: Optional[Annotated[str, StringConstraints(pattern=r'^[A-Za-z0-9\-]{8,}$')]] = None

#     @validator('file_id', always=True)
#     def check_file_id(cls, v):
#         if v and len(v) != 8:
#             raise ValueError('Invalid file ID: it must be exactly 8 digits.')
#         return v

#     lead_id: Optional[str] = None
#     other_data: Optional[Dict] = None


# # --------- helpers ----------
# def _merge_other_data(existing: Optional[Dict], incoming: Optional[Dict]) -> Optional[Dict]:
#     """
#     Merge arbitrary CRM-shaped other_data. Keeps existing keys and updates/overwrites with incoming.
#     Converts None values to "" for consistent UI rendering.
#     """
#     if incoming is None:
#         return existing
#     base = dict(existing or {})
#     for k, v in incoming.items():
#         base[str(k)] = "" if v is None else v
#     return base or None
# # ----------------------------------






# @router.put("/leads/{lead_id}")
# async def update_lead(
#     lead_id: int,
#     data: UpdateLeadPayload,
#     user: Annotated[User, Depends(get_current_user)],
# ):
#     # Only allow editing leads in the current user's files
#     lead = await Lead.filter(id=lead_id, file__user_id=user.id).first()
#     if not lead:
#         raise HTTPException(status_code=404, detail="Lead not found")

#     if data.file_id is not None:
#         file = await FileModel.filter(id=data.file_id, user_id=user.id).first()
#         if not file:
#             raise HTTPException(status_code=404, detail="File not found for this user")
#         lead.file = file

#     if data.first_name is not None:  lead.first_name = data.first_name
#     if data.last_name  is not None:  lead.last_name  = data.last_name
#     if data.email      is not None:  lead.email      = data.email
#     if data.mobile     is not None:  lead.mobile     = data.mobile
#     if data.salesforce_id is not None: lead.salesforce_id = data.salesforce_id
#     if data.add_date   is not None:  lead.add_date   = data.add_date

#     # keep ALL keys for flexible columns
#     if data.other_data is not None:
#         lead.other_data = _merge_other_data(lead.other_data, data.other_data)

#     await lead.save()
#     return {"success": True, "detail": "Lead updated successfully"}


# @router.post("/add-lead-to-api")
# async def add_to_dnc(payload: LeadInput, request: Request):
#     try:
#         file_instance = None
#         if payload.file_id:
#             file_instance = await FileModel.filter(alphanumeric_id=payload.file_id).first()
#             if not file_instance:
#                 raise HTTPException(status_code=404, detail="File not found for provided file_id.")

#         lead = await Lead.create(
#             first_name=payload.first_name,
#             last_name=payload.last_name,
#             email=payload.email,
#             add_date=datetime.now(),
#             mobile=payload.mobile,
#             salesforce_id=payload.lead_id,
#             other_data=payload.other_data,   # keep arbitrary keys
#             file=file_instance,
#             last_called_at=None,
#             dnc=False  # ensure visible in /leads
#         )
#         await lead.save()

#         return {'success': True, 'detail': 'Lead successfully added.'}

#     except HTTPException as http_e:
#         raise http_e
#     except Exception as e:
#         print(f"Unexpected error: {str(e)}")
#         raise HTTPException(status_code=400, detail="An unexpected error occurred while processing the request.")
        
# @router.post("/add_manually_lead")
# async def add_lead_manually( data: CreateLeadPayload, user: Annotated[User, Depends(get_current_user)]):
#     try:
#         if data.file_id:
#             file = await FileModel.filter(id=data.file_id).first()
#             if not file:
#                 raise HTTPException(status_code=404, detail="File not found")
        
#         formatted_other_data = _merge_other_data(None, data.other_data)

#         lead = await Lead.create(
#             first_name=data.first_name,
#             last_name=data.last_name,
#             email=data.email,
#             add_date=data.add_date,
#             mobile=data.mobile,
#             file_id=data.file_id,
#             salesforce_id=data.salesforce_id, 
#             other_data=formatted_other_data,
#             dnc=False
#         )
#         await lead.save()
#         return {"success": True, "detail": "Lead added successfully"}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
    
# @router.post("/create-list")
# async def create_list_manually(data: CreateFilePayload, user: Annotated[User, Depends(get_current_user)]):
#     try:
#         file_record = FileModel(
#             name=data.name,
#             user=user
#         )
#         await file_record.save()
        
#         return {
#             "success": True, 
#             "detail": "List created successfully",
#             "file": {
#                 "id": file_record.id,
#                 "name": file_record.name,
#                 "alphanumeric_id": file_record.alphanumeric_id,
#                 "created_at": file_record.created_at,
#                 "user_id": file_record.user_id
#             }
#         }
#     except HTTPException as e:
#         raise e
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
    
# @router.put("/update-lead-state/{leadId}")
# async def add_lead_manually( leadId: int, data:StateUpdateRequest , user: Annotated[User, Depends(get_current_user)], main_admin:User = Depends(get_user_admin)):
#     try:
#         states = stateandtimezone()
#         time_zones = {entry["name"] : entry['zone'] for entry in states}
#         state = data.state.strip().lower()

#         matching_state = next((state_name for state_name in time_zones if state in state_name.lower()), None)
#         lead = await Lead.filter(id = leadId).first()
#         if matching_state:
#            timezone = time_zones[matching_state]
#            lead.timezone = timezone
#            lead.state = data.state
#            await lead.save()
#            return {"success": True, "detail": "Lead updated successfully"}
#         else:
#            timezone = None
#            lead.timezone = timezone
#            await lead.save()
#            return {"success": False, "detail": "Unable to update lead. State is not correct"}
           
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
  

# def is_within_trial_period(user_free_trial_start: datetime, has_free_trial: bool) -> bool:
#     if user_free_trial_start is None:
#         print("trial is not started yet but can upload leads to complete the profile")
#         return True
    
#     print("trial started and check the and process to lead upload if with the trial")
#     user_free_trial_start = user_free_trial_start.replace(tzinfo=None)
#     trial_end_date = user_free_trial_start + timedelta(weeks=2)
#     current_time = datetime.now().replace(tzinfo=None)  
#     return has_free_trial and current_time < trial_end_date

# def count_leads_in_csv(content: str) -> int:
#     rows = [row for row in content.splitlines() if row.strip() != '']
#     return len(rows) - 1 if len(rows) > 0 else 0

# async def process_file_upload(content: str, file: UploadFile, name: str, user: User, trial_leads=None, message=None):
#     try:
#         file_record = FileModel(name=name, user=user)
#         await file_record.save()

#         results = await import_leads_csv(content, file_record)

#         return { 
#             "success": True,
#             "results": results,
#             "detail": humanize_results(results),
#             "message": message
#         }

#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Error processing file: {str(e)}"
#         )

# async def get_lead_count_for_user(user_id: int) -> int:
#     try:
#         files = await FileModel.filter(user_id=user_id).all()

#         file_ids = [file.id for file in files]

#         if file_ids:
#             leads = await Lead.filter(file_id__in=file_ids).all()
#             return len(leads)
#         else:
#             return 0
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error retrieving leads: {str(e)}")

# @router.post("/files")
# async def import_leads_file(user: Annotated[User, Depends(get_current_user)], 
#                              file: UploadFile = FastAPIFile(...), name: str = Form(...)):
#     try:  
#         content_bytes = await file.read()
#         content = content_bytes.decode("utf-8")
        
#         if file.filename.split(".")[-1] != "csv":
#             raise HTTPException(
#                 status_code=400,
#                 detail="Unsupported Format. Only CSV files are allowed."
#             )
#         return await process_file_upload(content, file, name, user)
    
#     except HTTPException as e:
#         raise e
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"An unexpected error occurred: {str(e)}"
#         )

# @router.get("/files")
# async def get_files(user: Annotated[User, Depends(get_current_user)]):
#     files = await FileModel.filter(user=user.id).all().order_by("-created_at")
#     files_with_leads_count = []
#     for file in files:
#         leads_count = await Lead.filter(file=file).count()
#         files_with_leads_count.append({
#             "id":file.id,
#             "name":file.name,
#             "alphanumeric_id":file.alphanumeric_id,
#             "created_at":file.created_at,
#             "is_syncing":file.is_syncing,
#             "sync_enable":file.sync_enable,
#             "sync_frequency":file.sync_frequency,
#             "leads_count": leads_count
#         })
#     return files_with_leads_count


# @router.delete("/files/{id}")
# async def delete_file(id: int,user: Annotated[User, Depends(get_current_user)]
# ):
#     file = await FileModel.get_or_none(id=id)
#     await file.delete()
#     # await Logs.create(
#     #             user = user,
#     #             message = f"deleted a file {file.name}",
#     #             short_message = "delete_file"
#     #         )
#     return { "success": True, "detail": "File deleted successfully." }

# @router.get("/admin_leads/{file_id}")
# async def leads(user: Annotated[User, Depends(get_current_user)],file_id: Optional[int] = None): 
#     try:
#         filters = {}
#         if file_id:
#             filters["file_id"] = file_id
       
#         leads = await Lead.filter(**filters).all()
#         file = await FileModel.filter(id=file_id).first()
#         if not file:
#             return[]
#         return leads
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

# @router.get("/leads")
# async def leads(user: Annotated[User, Depends(get_current_user)], file_id: Optional[int] = None):
#     print("lllll")
#     # include dnc False OR NULL so CRM-imported contacts (if dnc missing) still show
#     base_filters = { "file__user_id": user.id }
#     if file_id:
#         base_filters["file_id"] = file_id
#     return await Lead.filter(**base_filters, dnc__in=[False, None]).all().order_by("id")

# @router.get("/leads/{lead_id}")
# async def leads(user: Annotated[User, Depends(get_current_user)], lead_id:int):
#     print("lead_id", lead_id)
#     filters = { "file__user_id": user.id  }
#     if lead_id:
#         filters["id"] = lead_id
#     return await Lead.filter(**filters)

# @router.get("/admin/leads")
# async def leads(user: Annotated[User, Depends(get_current_user)],file_id: Optional[int] = None, user_id: Optional[int] = None): 
#     filters = { "file__user_id": user_id }
#     if file_id:
#         filters["file_id"] = file_id
#     return await Lead.filter(**filters).all()

# @router.delete("/leads")
# async def delete_lead(data: DeleteLeadPayload, user: Annotated[User, Depends(get_current_user)]):
#     leads = await Lead.filter(id__in=data.ids, file__user_id=user.id).all()
#     await asyncio.gather(*[lead.delete() for lead in leads])
#     return { 
#         "success": True, 
#         "detail": "Lead(s) deleted successfully." 
#     }

# @router.get("/all_leads/all_files")
# async def get_files(user: Annotated[User, Depends(get_admin)]):
#     files = await FileModel.all().prefetch_related("user__company").order_by("id")
#     return [{
#         **dict(file),
#         "user": file.user,
#         "company_name": file.user.company.company_name if file.user.company else None 
#     } for file in files]

# @router.get("/all_leads/all_files/{company_id}")
# async def get_files_by_company(company_id: int, user: Annotated[User, Depends(get_admin)]):
#     try:
#         files = await FileModel.filter(user__company__id=company_id).prefetch_related("user__company").order_by("id")
        
#         if not files:
#             raise HTTPException(status_code=404, detail="No files found for the given company ID.")
        
#         return [{
#             **dict(file),
#             "user": file.user,
#             "company_name": file.user.company.company_name if file.user.company else None
#         } for file in files]
    
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

# @router.post("/leads_from_url")
# async def import_files(
#     url: str, 
#     filename: str, 
#     user: Annotated[User, Depends(get_current_user)],
#     main_admin: Annotated[User, Depends(get_user_admin)],
#     auto_sync: Optional[bool] = False, 
#     sync_frequency: Optional[int] = False, 
# ):
#     async with AsyncClient() as client:
#         try:
#             response = await client.get(url)

#             if response.status_code != 200:
#                 raise HTTPException(status_code=response.status_code, detail="Failed to fetch URL content")

#             content_type = response.headers.get("Content-Type", "")
#             if "csv" not in content_type and not url.endswith(".csv"):
#                 raise HTTPException(status_code=400, detail="URL does not point to a CSV file")

#             content = response.text
            
#             file_record = FileModel(name=filename, user=main_admin , url=url, sync_enable= auto_sync, is_syncing =auto_sync,  sync_frequency = sync_frequency  )
#             await file_record.save()

#             results = await import_leads_csv(content, file_record)
#             # await Logs.create(
#             #     user = user,
#             #     message = f"imports a file from url : {url}",
#             #     short_message = "import_file"
#             # )
#             return {
#                 "success": True,
#                 "results": results,
#                 "detail": humanize_results(results)
#             }

#         except Exception as e:
#             raise HTTPException(status_code=500, detail=str(e))

# @router.post("/files/{selectedFile}/overwrite")
# async def import_files(url: str, selectedFile: int, user: Annotated[User, Depends(get_current_user)]):
#     overwrite_file = await FileModel.get_or_none(id=selectedFile)
    
#     if not overwrite_file:
#         raise HTTPException(status_code=404, detail="File not found")
    
#     async with AsyncClient() as client:
#         try:
#             response = await client.get(url)
#             if response.status_code != 200:
#                 raise HTTPException(status_code=response.status_code, detail="Failed to fetch URL content")

#             content_type = response.headers.get("Content-Type", "")
#             if "csv" not in content_type and not url.endswith(".csv"):
#                 raise HTTPException(status_code=400, detail="URL does not point to a CSV file")
            
#             content = response.text

#             await Lead.filter(file=overwrite_file).delete()

#             results = await import_leads_csv(content, file=overwrite_file)

#             # await Logs.create(
#             #     user=user,
#             #     message=f"overwrote file {overwrite_file.name} with data from URL: {url}",
#             #     short_message="overwrite_file"
#             # )

#             return {
#                 "success": True,
#                 "results": results,
#                 "detail": humanize_results(results)
#             }

#         except Exception as e:
#             raise HTTPException(status_code=500, detail=str(e))

# @router.post("/files/{selectedFile}/append")
# async def append_leads(url: str, selectedFile: int, user: Annotated[User, Depends(get_current_user)]):
#     append_file = await FileModel.get_or_none(id=selectedFile)
    
#     if not append_file:
#         raise HTTPException(status_code=404, detail="File not found")
    
#     async with AsyncClient() as client:
#         try:
#             response = await client.get(url)
#             if response.status_code != 200:
#                 raise HTTPException(status_code=response.status_code, detail="Failed to fetch URL content")

#             content_type = response.headers.get("Content-Type", "")
#             if "csv" not in content_type and not url.endswith(".csv"):
#                 raise HTTPException(status_code=400, detail="URL does not point to a CSV file")
            
#             content = response.text

#             results = await import_leads_csv(content, file=append_file)

#             # await Logs.create(
#             #     user=user,
#             #     message=f"appended leads to file {append_file.name} from URL: {url}",
#             #     short_message="append_file"
#             # )

#             return {
#                 "success": True,
#                 "results": results,
#                 "detail": humanize_results(results)
#             }

#         except Exception as e:
#             raise HTTPException(status_code=500, detail=str(e))
   
# @router.post("/sync/pause/{id}")
# async def syncPause(id : int ,user: Annotated[User, Depends(get_current_user)]):
#    try:
#         sync = await FileModel.get_or_none(id=id)
#         if not sync:
#             raise HTTPException(status_code=404, detail="Not found")
#         sync.is_syncing= False
#         await sync.save()
    
#         return {"success" : True , "detail" : "Automatic sync paused" }
#    except Exception as e:
#             raise HTTPException(status_code=500, detail=str(e))
   
# @router.post("/sync/resume/{id}")
# async def syncResume(id : int ,user: Annotated[User, Depends(get_current_user)]):
#     try:
#         sync = await FileModel.get_or_none(id=id)
#         if not sync:
#             raise HTTPException(status_code=404, detail="Not found")
#         sync.is_syncing= True
#         await sync.save()
    
#         return {"success" : True , "detail" : "Automatic sync resumed" }
#     except Exception as e:
#             raise HTTPException(status_code=500, detail=str(e))

# @router.get("/sync/status")
# async def syncResume():
#    return scheduler_status.sync_paused


# # -------- NEW: dynamic column discovery for a file ----------
# @router.get("/files/{file_id}/dynamic-columns")
# async def get_dynamic_columns(file_id: int, user: Annotated[User, Depends(get_current_user)]):
#     """
#     Returns the union of keys present in Lead.other_data for this file.
#     Use this to render flexible, CRM-named columns in the UI.
#     """
#     file = await FileModel.get_or_none(id=file_id, user_id=user.id)
#     if not file:
#         raise HTTPException(status_code=404, detail="File not found")

#     leads = await Lead.filter(file_id=file_id).all()
#     keys: Set[str] = set()
#     for l in leads:
#         if isinstance(l.other_data, dict):
#             for k in l.other_data.keys():
#                 if k:
#                     keys.add(str(k))

#         # soft cap to avoid huge responses
#         if len(keys) >= 200:
#             break

#     # Move known columns to top if present
#     preferred = ["firstname", "lastname", "FirstName", "LastName", "email", "Email", "phone", "Phone", "company", "Company"]
#     ordered = [k for k in preferred if k in keys] + sorted([k for k in keys if k not in preferred])
#     return {"file_id": file_id, "columns": ordered}


# # ============== NEW: Ingest HubSpot contacts as leads into "Hubspot Leads" =================
# HUBSPOT_CONTACT_PROPS = "firstname,lastname,email,phone,company,hs_object_id,createdate,lastmodifieddate"

# def _merge_other_data(existing: Optional[Dict], incoming: Optional[Dict]) -> Optional[Dict]:
#     base = dict(existing or {})
#     if incoming:
#         for k, v in incoming.items():
#             base[str(k)] = "" if v is None else v
#     return base or None

# async def _ensure_file(user: User, name: str) -> FileModel:
#     file = await FileModel.get_or_none(user_id=user.id, name=name)
#     if not file:
#         file = FileModel(name=name, user=user)
#         await file.save()
#     return file

# @router.post("/crm/ingest/hubspot")
# async def ingest_hubspot_contacts(user: Annotated[User, Depends(get_current_user)]):
#     """
#     Pulls ALL HubSpot contacts and upserts them as LEADS into 'Hubspot Leads'.
#     Uses refreshed token and retries once on 401.
#     """
#     # IMPORTANT: this call refreshes the token if expired
#     acc = await _get_active_account(user, "hubspot")

#     file = await _ensure_file(user, "Hubspot Leads")

#     created = 0
#     updated = 0
#     after: Optional[str] = None
#     limit = 100

#     def _headers(token: str) -> Dict[str, str]:
#         return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

#     async with AsyncClient(timeout=30.0) as client:
#         while True:
#             params = {"limit": limit, "properties": HUBSPOT_CONTACT_PROPS}
#             if after:
#                 params["after"] = after

#             # first attempt with (possibly refreshed) token
#             r = await client.get(
#                 "https://api.hubapi.com/crm/v3/objects/contacts",
#                 headers=_headers(acc.access_token),
#                 params=params,
#             )

#             # if token got invalid between refresh+call, try one refresh+retry
#             if r.status_code == 401:
#                 before = acc.access_token
#                 acc = await _ensure_fresh_token("hubspot", acc)
#                 if acc.access_token != before:
#                     r = await client.get(
#                         "https://api.hubapi.com/crm/v3/objects/contacts",
#                         headers=_headers(acc.access_token),
#                         params=params,
#                     )
#                 if r.status_code == 401:
#                     # still unauthorized after refresh
#                     raise HTTPException(401, f"HubSpot contacts fetch failed after refresh: {r.text}")

#             if not r.is_success:
#                 raise HTTPException(r.status_code, f"HubSpot contacts fetch failed: {r.text}")

#             j = r.json()
#             for o in j.get("results", []):
#                 props = o.get("properties") or {}
#                 first = props.get("firstname") or ""
#                 last = props.get("lastname") or ""
#                 email = props.get("email")
#                 phone = props.get("phone")
#                 external_id = str(o.get("id"))

#                 existing = await Lead.get_or_none(file_id=file.id, salesforce_id=external_id)
#                 if existing:
#                     changed = False
#                     if existing.first_name != first: existing.first_name = first; changed = True
#                     if existing.last_name  != last:  existing.last_name  = last;  changed = True
#                     if existing.email      != email: existing.email      = email; changed = True
#                     if existing.mobile     != phone: existing.mobile     = phone; changed = True
#                     merged = _merge_other_data(existing.other_data, props)
#                     if merged != existing.other_data:
#                         existing.other_data = merged; changed = True
#                     if existing.dnc not in (False, None):
#                         existing.dnc = False; changed = True
#                     if changed:
#                         await existing.save()
#                         updated += 1
#                 else:
#                     await Lead.create(
#                         first_name=first,
#                         last_name=last,
#                         email=email,
#                         add_date=datetime.now(),
#                         mobile=phone,
#                         file=file,
#                         salesforce_id=external_id,
#                         other_data=dict(props),  # keep CRM field names for flexible columns
#                         dnc=False
#                     )
#                     created += 1

#             after = ((j.get("paging") or {}).get("next") or {}).get("after")
#             if not after:
#                 break

#     total_in_file = await Lead.filter(file=file).count()
#     return {
#         "success": True,
#         "file_id": file.id,
#         "file_name": file.name,
#         "created": created,
#         "updated": updated,
#         "total_in_file": total_in_file
#     }
    
    
from urllib.parse import urlparse
from fastapi import APIRouter, Form, UploadFile, File as FastAPIFile, HTTPException, Depends, Request
from controllers.crm_controller import _ensure_fresh_token, _get_active_account
from helpers.get_admin import get_admin
from helpers.get_user_admin import get_user_admin
from helpers.import_leads_csv import import_leads_csv, humanize_results
from helpers.state import stateandtimezone
from models.lead import Lead
from models.auth import User
from models.file import File as FileModel
from models.crm import IntegrationAccount
from pydantic import BaseModel, EmailStr, StringConstraints, validator
from typing import List, Optional, Dict, Set, Annotated
from httpx import AsyncClient
from helpers.token_helper import get_current_user
import asyncio
from datetime import datetime, timedelta
from controllers.campaign_controller import trigger_campaign_refresh_for_file

router = APIRouter()

HUBSPOT_CONTACT_PROPS = "firstname,lastname,email,phone,company,hs_object_id,createdate,lastmodifieddate"

# =========================
#         Schemas
# =========================
class DeleteLeadPayload(BaseModel):
    ids: List[int]

class StateUpdateRequest(BaseModel):
    state: str

class CreateLeadPayload(BaseModel):
    first_name: str
    last_name: str
    email: str
    add_date: str
    mobile: str
    file_id: Optional[int]
    salesforce_id: str
    other_data: Optional[Dict[str, str]] = None

class CreateFilePayload(BaseModel):
    name: str

class UpdateLeadPayload(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    mobile: Optional[str] = None
    salesforce_id: Optional[str] = None
    add_date: Optional[str] = None
    file_id: Optional[int] = None
    other_data: Optional[Dict[str, str]] = None

# NOTE: we keep typing.Annotated for FastAPI Depends,
# and reuse it below for constraints as well.
class LeadInput(BaseModel):
    api_key: str
    first_name: str
    last_name: str
    email: EmailStr
    mobile: Annotated[str, StringConstraints(min_length=10, max_length=10, pattern=r'^\d{10}$')]
    file_id: Optional[Annotated[str, StringConstraints(pattern=r'^[A-Za-z0-9\-]{8,}$')]] = None

    @validator('file_id', always=True)
    def check_file_id(cls, v):
        if v and len(v) != 8:
            raise ValueError('Invalid file ID: it must be exactly 8 digits.')
        return v

    lead_id: Optional[str] = None
    other_data: Optional[Dict] = None


# =========================
#        Helpers
# =========================
def _merge_other_data(existing: Optional[Dict], incoming: Optional[Dict]) -> Optional[Dict]:
    if incoming is None:
        return existing
    base = dict(existing or {})
    for k, v in incoming.items():
        base[str(k)] = "" if v is None else v
    return base or None

def infer_origin_from_file(file: Optional[FileModel]) -> str:
    """
    Decide origin solely by the *file*:
      - 'Hubspot Leads'  -> 'HubSpot CRM'
      - 'GHL Leads'      -> 'GHL CRM'
      - 'Monday Leads'   -> 'Monday CRM'
      - anything else    -> 'CSV' (manual/csv/api)
    """
    if not file or not file.name:
        return "CSV"
    n = file.name.strip().lower()
    if "hubspot leads" in n:
        return "HubSpot CRM"
    if "ghl leads" in n:
        return "GHL CRM"
    if "monday leads" in n:
        return "Monday CRM"
    return "CSV"

async def _ensure_file(user: User, name: str) -> FileModel:
    file = await FileModel.get_or_none(user_id=user.id, name=name)
    if not file:
        file = FileModel(name=name, user=user)
        await file.save()
    return file


# =========================
#      Lead Endpoints
# =========================
@router.put("/leads/{lead_id}")
async def update_lead(
    lead_id: int,
    data: UpdateLeadPayload,
    user: Annotated[User, Depends(get_current_user)],
):
    lead = await Lead.filter(id=lead_id, file__user_id=user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if data.file_id is not None:
        file = await FileModel.filter(id=data.file_id, user_id=user.id).first()
        if not file:
            raise HTTPException(status_code=404, detail="File not found for this user")
        lead.file = file
        # if file changed, recompute origin by file rule
        lead.origin = infer_origin_from_file(file)

    if data.first_name is not None:  lead.first_name = data.first_name
    if data.last_name  is not None:  lead.last_name  = data.last_name
    if data.email      is not None:  lead.email      = data.email
    if data.mobile     is not None:  lead.mobile     = data.mobile
    if data.salesforce_id is not None: lead.salesforce_id = data.salesforce_id
    if data.add_date   is not None:  lead.add_date   = data.add_date

    if data.other_data is not None:
        lead.other_data = _merge_other_data(lead.other_data, data.other_data)

    await lead.save()
    return {"success": True, "detail": "Lead updated successfully"}


@router.post("/add-lead-to-api")
async def add_to_dnc(payload: LeadInput, request: Request):
    """
    Public API add — origin is derived from file (if provided) else CSV.
    """
    try:
        file_instance = None
        if payload.file_id:
            file_instance = await FileModel.filter(alphanumeric_id=payload.file_id).first()
            if not file_instance:
                raise HTTPException(status_code=404, detail="File not found for provided file_id.")

        origin = infer_origin_from_file(file_instance)

        lead = await Lead.create(
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=payload.email,
            add_date=datetime.now(),
            mobile=payload.mobile,
            salesforce_id=payload.lead_id,
            other_data=payload.other_data,
            file=file_instance,
            last_called_at=None,
            dnc=False,
            origin=origin
        )
        await lead.save()
        return {'success': True, 'detail': 'Lead successfully added.'}

    except HTTPException as http_e:
        raise http_e
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=400, detail="An unexpected error occurred while processing the request.")
        

@router.post("/add_manually_lead")
async def add_lead_manually(data: CreateLeadPayload, user: Annotated[User, Depends(get_current_user)]):
    """
    Manual add — origin derived from file else CSV.
    """
    try:
        file = None
        if data.file_id:
            file = await FileModel.filter(id=data.file_id, user_id=user.id).first()
            if not file:
                raise HTTPException(status_code=404, detail="File not found")

        origin = infer_origin_from_file(file)
        formatted_other_data = _merge_other_data(None, data.other_data)

        lead = await Lead.create(
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email,
            add_date=data.add_date,
            mobile=data.mobile,
            file_id=data.file_id,
            salesforce_id=data.salesforce_id, 
            other_data=formatted_other_data,
            dnc=False,
            origin=origin
        )
        await lead.save()
        return {"success": True, "detail": "Lead added successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


@router.post("/create-list")
async def create_list_manually(data: CreateFilePayload, user: Annotated[User, Depends(get_current_user)]):
    try:
        file_record = FileModel(name=data.name, user=user)
        await file_record.save()
        return {
            "success": True, 
            "detail": "List created successfully",
            "file": {
                "id": file_record.id,
                "name": file_record.name,
                "alphanumeric_id": file_record.alphanumeric_id,
                "created_at": file_record.created_at,
                "user_id": file_record.user_id
            }
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
    

@router.put("/update-lead-state/{leadId}")
async def add_lead_state(leadId: int, data: StateUpdateRequest,
                         user: Annotated[User, Depends(get_current_user)],
                         main_admin: User = Depends(get_user_admin)):
    try:
        states = stateandtimezone()
        time_zones = {entry["name"] : entry['zone'] for entry in states}
        state = data.state.strip().lower()

        matching_state = next((state_name for state_name in time_zones if state in state_name.lower()), None)
        lead = await Lead.filter(id=leadId).first()
        if matching_state:
            timezone = time_zones[matching_state]
            lead.timezone = timezone
            lead.state = data.state
            await lead.save()
            return {"success": True, "detail": "Lead updated successfully"}
        else:
            lead.timezone = None
            await lead.save()
            return {"success": False, "detail": "Unable to update lead. State is not correct"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


# =========================
#      CSV Utilities
# =========================
def is_within_trial_period(user_free_trial_start: datetime, has_free_trial: bool) -> bool:
    if user_free_trial_start is None:
        return True
    user_free_trial_start = user_free_trial_start.replace(tzinfo=None)
    trial_end_date = user_free_trial_start + timedelta(weeks=2)
    current_time = datetime.now().replace(tzinfo=None)  
    return has_free_trial and current_time < trial_end_date

def count_leads_in_csv(content: str) -> int:
    rows = [row for row in content.splitlines() if row.strip() != '']
    return len(rows) - 1 if len(rows) > 0 else 0


async def process_file_upload(content: str, file: UploadFile, name: str, user: User, trial_leads=None, message=None):
    """
    CSV Upload helper => import + tag leads by file rule (CRM files → CRM origin; else CSV)
    """
    try:
        file_record = FileModel(name=name, user=user)
        await file_record.save()

        results = await import_leads_csv(content, file_record)

        # Tag all leads in this file according to file name
        await Lead.filter(file=file_record).update(origin=infer_origin_from_file(file_record))

        return { 
            "success": True,
            "results": results,
            "detail": humanize_results(results),
            "message": message
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


async def get_lead_count_for_user(user_id: int) -> int:
    try:
        files = await FileModel.filter(user_id=user_id).all()
        file_ids = [file.id for file in files]
        if file_ids:
            leads = await Lead.filter(file_id__in=file_ids).all()
            return len(leads)
        else:
            return 0
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving leads: {str(e)}")


@router.post("/files")
async def import_leads_file(user: Annotated[User, Depends(get_current_user)], 
                             file: UploadFile = FastAPIFile(...), name: str = Form(...)):
    try:  
        content_bytes = await file.read()
        content = content_bytes.decode("utf-8")
        if file.filename.split(".")[-1] != "csv":
            raise HTTPException(status_code=400, detail="Unsupported Format. Only CSV files are allowed.")
        return await process_file_upload(content, file, name, user)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")


@router.get("/files")
async def get_files(user: Annotated[User, Depends(get_current_user)]):
    files = await FileModel.filter(user=user.id).all().order_by("-created_at")
    files_with_leads_count = []
    for file in files:
        leads_count = await Lead.filter(file=file).count()
        files_with_leads_count.append({
            "id":file.id,
            "name":file.name,
            "alphanumeric_id":file.alphanumeric_id,
            "created_at":file.created_at,
            "is_syncing":file.is_syncing,
            "sync_enable":file.sync_enable,
            "sync_frequency":file.sync_frequency,
            "leads_count": leads_count
        })
    return files_with_leads_count


@router.delete("/files/{id}")
async def delete_file(id: int, user: Annotated[User, Depends(get_current_user)]):
    file = await FileModel.get_or_none(id=id)
    await file.delete()
    return { "success": True, "detail": "File deleted successfully." }

# =========================
#       Lead Lists
# =========================
@router.get("/admin_leads/{file_id}")
async def leads_admin(user: Annotated[User, Depends(get_current_user)], file_id: Optional[int] = None): 
    try:
        filters = {}
        if file_id:
            filters["file_id"] = file_id
        leads = await Lead.filter(**filters).all()
        file = await FileModel.filter(id=file_id).first()
        if not file:
            return []
        return leads
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/leads")
async def leads(user: Annotated[User, Depends(get_current_user)], file_id: Optional[int] = None, origin: Optional[str] = None):
    """
    Get user's leads; optionally filter by file_id and/or origin.
    origin can be: 'CSV', 'HubSpot CRM', 'GHL CRM', 'Monday CRM'
    """
    base_filters = {"file__user_id": user.id}
    if file_id:
        base_filters["file_id"] = file_id
    if origin:
        base_filters["origin"] = origin
    return await Lead.filter(**base_filters, dnc__in=[False, None]).all().order_by("id")

@router.get("/leads/{lead_id}")
async def lead_by_id(user: Annotated[User, Depends(get_current_user)], lead_id:int):
    filters = { "file__user_id": user.id, "id": lead_id }
    return await Lead.filter(**filters)

@router.get("/admin/leads")
async def leads_admin_multi(user: Annotated[User, Depends(get_current_user)], file_id: Optional[int] = None, user_id: Optional[int] = None): 
    filters = { "file__user_id": user_id }
    if file_id:
        filters["file_id"] = file_id
    return await Lead.filter(**filters).all()

@router.delete("/leads")
async def delete_lead(data: DeleteLeadPayload, user: Annotated[User, Depends(get_current_user)]):
    leads = await Lead.filter(id__in=data.ids, file__user_id=user.id).all()
    await asyncio.gather(*[lead.delete() for lead in leads])
    return { "success": True, "detail": "Lead(s) deleted successfully." }

@router.get("/all_leads/all_files")
async def get_files_all(user: Annotated[User, Depends(get_admin)]):
    files = await FileModel.all().prefetch_related("user__company").order_by("id")
    return [{
        **dict(file),
        "user": file.user,
        "company_name": file.user.company.company_name if file.user.company else None 
    } for file in files]

@router.get("/all_leads/all_files/{company_id}")
async def get_files_by_company(company_id: int, user: Annotated[User, Depends(get_admin)]):
    try:
        files = await FileModel.filter(user__company__id=company_id).prefetch_related("user__company").order_by("id")
        if not files:
            raise HTTPException(status_code=404, detail="No files found for the given company ID.")
        return [{
            **dict(file),
            "user": file.user,
            "company_name": file.user.company.company_name if file.user.company else None
        } for file in files]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

# =========================
#     CSV via URL / overwrite / append
# =========================
@router.post("/leads_from_url")
async def import_files(
    url: str, 
    filename: str, 
    user: Annotated[User, Depends(get_current_user)],
    main_admin: Annotated[User, Depends(get_user_admin)],
    auto_sync: Optional[bool] = False, 
    sync_frequency: Optional[int] = False, 
):
    async with AsyncClient() as client:
        try:
            response = await client.get(url)
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="Failed to fetch URL content")

            content_type = response.headers.get("Content-Type", "")
            if "csv" not in content_type and not url.endswith(".csv"):
                raise HTTPException(status_code=400, detail="URL does not point to a CSV file")

            content = response.text
            
            file_record = FileModel(name=filename, user=main_admin, url=url,
                                    sync_enable=auto_sync, is_syncing=auto_sync, sync_frequency=sync_frequency)
            await file_record.save()

            results = await import_leads_csv(content, file_record)

            # Tag by file rule (CRM-named files → CRM origin; else CSV)
            await Lead.filter(file=file_record).update(origin=infer_origin_from_file(file_record))

            return {
                "success": True,
                "results": results,
                "detail": humanize_results(results)
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

@router.post("/files/{selectedFile}/overwrite")
async def import_files_overwrite(url: str, selectedFile: int, user: Annotated[User, Depends(get_current_user)]):
    overwrite_file = await FileModel.get_or_none(id=selectedFile)
    if not overwrite_file:
        raise HTTPException(status_code=404, detail="File not found")
    
    async with AsyncClient() as client:
        try:
            response = await client.get(url)
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="Failed to fetch URL content")

            content_type = response.headers.get("Content-Type", "")
            if "csv" not in content_type and not url.endswith(".csv"):
                raise HTTPException(status_code=400, detail="URL does not point to a CSV file")
            
            content = response.text

            await Lead.filter(file=overwrite_file).delete()
            results = await import_leads_csv(content, file=overwrite_file)

            # Tag by file rule
            await Lead.filter(file=overwrite_file).update(origin=infer_origin_from_file(overwrite_file))

            return {
                "success": True,
                "results": results,
                "detail": humanize_results(results)
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

@router.post("/files/{selectedFile}/append")
async def append_leads(url: str, selectedFile: int, user: Annotated[User, Depends(get_current_user)]):
    append_file = await FileModel.get_or_none(id=selectedFile)
    if not append_file:
        raise HTTPException(status_code=404, detail="File not found")
    
    async with AsyncClient() as client:
        try:
            response = await client.get(url)
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="Failed to fetch URL content")

            content_type = response.headers.get("Content-Type", "")
            if "csv" not in content_type and not url.endswith(".csv"):
                raise HTTPException(status_code=400, detail="URL does not point to a CSV file")
            
            content = response.text

            results = await import_leads_csv(content, file=append_file)

            # Tag by file rule
            await Lead.filter(file=append_file).update(origin=infer_origin_from_file(append_file))

            return {
                "success": True,
                "results": results,
                "detail": humanize_results(results)
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

# =========================
#   Sync pause/resume
# =========================
@router.post("/sync/pause/{id}")
async def syncPause(id: int, user: Annotated[User, Depends(get_current_user)]):
    try:
        sync = await FileModel.get_or_none(id=id)
        if not sync:
            raise HTTPException(status_code=404, detail="Not found")
        sync.is_syncing = False
        await sync.save()
        return {"success": True, "detail": "Automatic sync paused"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
   
@router.post("/sync/resume/{id}")
async def syncResume(id: int, user: Annotated[User, Depends(get_current_user)]):
    try:
        sync = await FileModel.get_or_none(id=id)
        if not sync:
            raise HTTPException(status_code=404, detail="Not found")
        sync.is_syncing = True
        await sync.save()
        return {"success": True, "detail": "Automatic sync resumed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sync/status")
async def syncStatus():
    # return scheduler_status.sync_paused  # uncomment if you wire scheduler_status
    return {"supported": True}

# -------- dynamic column discovery ----------
@router.get("/files/{file_id}/dynamic-columns")
async def get_dynamic_columns(file_id: int, user: Annotated[User, Depends(get_current_user)]):
    file = await FileModel.get_or_none(id=file_id, user_id=user.id)
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    leads = await Lead.filter(file_id=file_id).all()
    keys: Set[str] = set()
    for l in leads:
        if isinstance(l.other_data, dict):
            for k in l.other_data.keys():
                if k:
                    keys.add(str(k))
        if len(keys) >= 200:
            break

    preferred = ["firstname", "lastname", "FirstName", "LastName", "email", "Email", "phone", "Phone", "company", "Company"]
    ordered = [k for k in preferred if k in keys] + sorted([k for k in keys if k not in preferred])
    return {"file_id": file_id, "columns": ordered}


# ============== HubSpot Ingest (CRM → File + Origin by file) =================
@router.post("/crm/ingest/hubspot")
async def ingest_hubspot_contacts(user: Annotated[User, Depends(get_current_user)]):
    """
    Pull all HubSpot contacts and upsert as leads into 'Hubspot Leads'.
    Origin tagging follows file rule → 'HubSpot CRM'.
    """
    acc = await _get_active_account(user, "hubspot")
    file = await _ensure_file(user, "Hubspot Leads")

    created = 0
    updated = 0
    after: Optional[str] = None
    limit = 100

    def _headers(token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    async with AsyncClient(timeout=30.0) as client:
        while True:
            params = {"limit": limit, "properties": HUBSPOT_CONTACT_PROPS}
            if after:
                params["after"] = after

            r = await client.get(
                "https://api.hubapi.com/crm/v3/objects/contacts",
                headers=_headers(acc.access_token),
                params=params,
            )

            if r.status_code == 401:
                before = acc.access_token
                acc = await _ensure_fresh_token("hubspot", acc)
                if acc.access_token != before:
                    r = await client.get(
                        "https://api.hubapi.com/crm/v3/objects/contacts",
                        headers=_headers(acc.access_token),
                        params=params,
                    )
                if r.status_code == 401:
                    raise HTTPException(401, f"HubSpot contacts fetch failed after refresh: {r.text}")

            if not r.is_success:
                raise HTTPException(r.status_code, f"HubSpot contacts fetch failed: {r.text}")

            j = r.json()
            for o in j.get("results", []):
                props = o.get("properties") or {}
                first = props.get("firstname") or ""
                last = props.get("lastname") or ""
                email = props.get("email")
                phone = props.get("phone")
                external_id = str(o.get("id"))

                existing = await Lead.get_or_none(file_id=file.id, salesforce_id=external_id)
                if existing:
                    changed = False
                    if existing.first_name != first: existing.first_name = first; changed = True
                    if existing.last_name  != last:  existing.last_name  = last;  changed = True
                    if existing.email      != email: existing.email      = email; changed = True
                    if existing.mobile     != phone: existing.mobile     = phone; changed = True
                    merged = _merge_other_data(existing.other_data, props)
                    if merged != existing.other_data:
                        existing.other_data = merged; changed = True
                    if existing.dnc not in (False, None):
                        existing.dnc = False; changed = True

                    # origin strictly by file:
                    new_origin = infer_origin_from_file(file)
                    if existing.origin != new_origin:
                        existing.origin = new_origin; changed = True

                    if changed:
                        await existing.save()
                        updated += 1
                else:
                    await Lead.create(
                        first_name=first,
                        last_name=last,
                        email=email,
                        add_date=datetime.now(),
                        mobile=phone,
                        file=file,
                        salesforce_id=external_id,
                        other_data=dict(props),
                        dnc=False,
                        origin=infer_origin_from_file(file)  # → "HubSpot CRM"
                    )
                    created += 1

            after = ((j.get("paging") or {}).get("next") or {}).get("after")
            if not after:
                break

    # Safety pass: ensure every lead in this file has the correct origin
    await Lead.filter(file=file).update(origin=infer_origin_from_file(file))

    total_in_file = await Lead.filter(file=file).count()
    return {
        "success": True,
        "file_id": file.id,
        "file_name": file.name,
        "created": created,
        "updated": updated,
        "total_in_file": total_in_file
    }
# --- imports (near the top of lead_controller.py) ---
from fastapi import APIRouter, Form, UploadFile, File as FastAPIFile, HTTPException, Depends, Request, Query
# ...
from typing import List, Optional, Dict, Set, Annotated, Any   # ← add Any here


@router.get("/leads/all/full")
async def all_leads_full(
    user: Annotated[User, Depends(get_current_user)],
    include_dnc: bool = Query(False, description="Include DNC=true leads as well"),
    origin: Optional[str] = Query(None, description="Filter by origin: CSV | HubSpot CRM | GHL CRM | Monday CRM"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """
    Return ALL leads across ALL files for the current user, with full details + file info.
    Supports optional origin filter, include_dnc, pagination (limit/offset).
    """
    filters: Dict[str, Any] = {"file__user_id": user.id}
    if not include_dnc:
        filters["dnc__in"] = [False, None]
    if origin:
        filters["origin"] = origin

    total = await Lead.filter(**filters).count()

    # Pull the page and include file metadata
    leads = await (
        Lead.filter(**filters)
        .prefetch_related("file")
        .order_by("id")
        .offset(offset)
        .limit(limit)
    )

    def _lead_row(l: Lead) -> Dict[str, Any]:
        f = getattr(l, "file", None)
        return {
            "id": l.id,
            "first_name": l.first_name,
            "last_name": l.last_name,
            "email": l.email,
            "mobile": l.mobile,
            "state": l.state,
            "timezone": l.timezone,
            "dnc": l.dnc,
            "submit_for_approval": l.submit_for_approval,
            "last_called_at": l.last_called_at,
            "call_count": l.call_count,
            "add_date": l.add_date,
            "salesforce_id": l.salesforce_id,
            "other_data": l.other_data,
            "created_at": l.created_at,
            "updated_at": l.updated_at,
            "origin": l.origin,
            "origin_meta": l.origin_meta,
            "file": None if not f else {
                "id": f.id,
                "name": f.name,
                "alphanumeric_id": getattr(f, "alphanumeric_id", None),
                "created_at": f.created_at,
                "user_id": f.user_id,
                "is_syncing": getattr(f, "is_syncing", None),
                "sync_enable": getattr(f, "sync_enable", None),
                "sync_frequency": getattr(f, "sync_frequency", None),
            },
        }

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_lead_row(l) for l in leads],
    }
