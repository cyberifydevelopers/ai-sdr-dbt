from urllib.parse import urlparse
from fastapi import APIRouter, Form, UploadFile, File as FastAPIFile, HTTPException, Depends,Request
# from helpers.criteria_check import has_payment_method
from helpers.get_admin import get_admin
from helpers.get_user_admin import get_user_admin
from helpers.import_leads_csv import import_leads_csv, humanize_results
from helpers.state import stateandtimezone
from models.lead import Lead
# from models.logs import Logs
from models.auth import User
from models.file import File as FileModel
from pydantic import BaseModel
from typing import List, Annotated, Optional
from httpx import AsyncClient
from helpers.token_helper import get_current_user
import asyncio
# from config import scheduler_status
from datetime import datetime, timedelta
# from models.dnc_api_key import DNCAPIkey
from typing import Annotated, Optional, Dict
from pydantic import BaseModel, EmailStr, StringConstraints
from pydantic import BaseModel, EmailStr, validator
from typing import Optional, Dict
from pydantic import StringConstraints
from typing_extensions import Annotated

router = APIRouter()

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



@router.put("/leads/{lead_id}")
async def update_lead(
    lead_id: int,
    data: UpdateLeadPayload,
    user: Annotated[User, Depends(get_current_user)],
):
    # Only allow editing leads in the current user's files
    lead = await Lead.filter(id=lead_id, file__user_id=user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if data.file_id is not None:
        file = await FileModel.filter(id=data.file_id, user_id=user.id).first()
        if not file:
            raise HTTPException(status_code=404, detail="File not found for this user")
        lead.file = file

    if data.first_name is not None:  lead.first_name = data.first_name
    if data.last_name  is not None:  lead.last_name  = data.last_name
    if data.email      is not None:  lead.email      = data.email
    if data.mobile     is not None:  lead.mobile     = data.mobile
    if data.salesforce_id is not None: lead.salesforce_id = data.salesforce_id
    if data.add_date   is not None:  lead.add_date   = data.add_date

    if data.other_data is not None:
        lead.other_data = {
            "Custom_0": data.other_data.get("Custom_0", ""),
            "Custom_1": data.other_data.get("Custom_1", ""),
        }

    await lead.save()
    return {"success": True, "detail": "Lead updated successfully"}


@router.post("/add-lead-to-api")
async def add_to_dnc(payload: LeadInput, request: Request):
    try:
        # api_key_record = await DNCAPIkey.filter(api_key=payload.api_key).first()
        # if not api_key_record:
        #     raise HTTPException(status_code=404, detail="API Key not found.")

        # is_private = api_key_record.visibility == "private"
        # client_ip = request.client.host
        # if is_private and client_ip not in api_key_record.allowed_ips:
        #     raise HTTPException(status_code=403, detail="Forbidden: IP not allowed for private key.")

        file_instance = None
        if payload.file_id:
            file_instance = await FileModel.filter(alphanumeric_id=payload.file_id).first()
            if not file_instance:
                raise HTTPException(status_code=404, detail="File not found for provided file_id.")

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
        )
        await lead.save()

        return {'success': True, 'detail': 'Lead successfully added.'}

    except HTTPException as http_e:
        raise http_e
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=400, detail="An unexpected error occurred while processing the request.")
        
@router.post("/add_manually_lead")
async def add_lead_manually( data: CreateLeadPayload, user: Annotated[User, Depends(get_current_user)]):
    try:
        # payment_method = await has_payment_method(main_admin)
        # if not payment_method:
        #    return {
        #         "success":False,
        #         "detail": f"Unable to add lead. You should have an active payment method first.",
        #     }
        if data.file_id:
            file = await FileModel.filter(id=data.file_id).first()
            if not file:
                raise HTTPException(status_code=404, detail="File not found")
        
        # Format other_data as object with Custom_0 and Custom_1 fields
        formatted_other_data = None
        if data.other_data:
            formatted_other_data = {
                "Custom_0": data.other_data.get("Custom_0", ""),
                "Custom_1": data.other_data.get("Custom_1", "")
            }
            
        lead = await Lead.create(
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email,
            add_date=data.add_date,
            mobile=data.mobile,
            file_id=data.file_id,
            salesforce_id= data.salesforce_id, 
            other_data=formatted_other_data
        )
        await lead.save()
        return {"success": True, "detail": "Lead added successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
    
@router.post("/create-list")
async def create_list_manually(data: CreateFilePayload, user: Annotated[User, Depends(get_current_user)]):
    try:
        # Create the list record
        file_record = FileModel(
            name=data.name,
            user=user
        )
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
async def add_lead_manually( leadId: int, data:StateUpdateRequest , user: Annotated[User, Depends(get_current_user)], main_admin:User = Depends(get_user_admin)):
    try:
        states = stateandtimezone()
        time_zones = {entry["name"] : entry['zone'] for entry in states}
        state = data.state.strip().lower()

        matching_state = next((state_name for state_name in time_zones if state in state_name.lower()), None)
        lead = await Lead.filter(id = leadId).first()
        if matching_state:
           timezone = time_zones[matching_state]
           lead.timezone = timezone
           lead.state = data.state
           await lead.save()
           return {"success": True, "detail": "Lead updated successfully"}
        else:
           timezone = None
           lead.timezone = timezone
           await lead.save()
           return {"success": False, "detail": "Unable to update lead. State is not correct"}
           

        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
  

def is_within_trial_period(user_free_trial_start: datetime, has_free_trial: bool) -> bool:
    if user_free_trial_start is None:
        print("trial is not started yet but can upload leads to complete the profile")
        return True
    
    print("trial started and check the and process to lead upload if with the trial")
    user_free_trial_start = user_free_trial_start.replace(tzinfo=None)
    trial_end_date = user_free_trial_start + timedelta(weeks=2)
    current_time = datetime.now().replace(tzinfo=None)  
    return has_free_trial and current_time < trial_end_date

def count_leads_in_csv(content: str) -> int:
    rows = [row for row in content.splitlines() if row.strip() != '']
    return len(rows) - 1 if len(rows) > 0 else 0

async def process_file_upload(content: str, file: UploadFile, name: str, user: User, trial_leads=None, message=None):
    try:
  
        file_record = FileModel(name=name, user=user)
        await file_record.save()

        results = await import_leads_csv(content, file_record)

        return { 
            "success": True,
            "results": results,
            "detail": humanize_results(results),
            "message": message
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing file: {str(e)}"
        )

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
            raise HTTPException(
                status_code=400,
                detail="Unsupported Format. Only CSV files are allowed."
            )

 
        return await process_file_upload(content, file, name, user)
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {str(e)}"
        )

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
async def delete_file(id: int,user: Annotated[User, Depends(get_current_user)]
):
    file = await FileModel.get_or_none(id=id)
  
    await file.delete()
    # await Logs.create(
    #             user = user,
    #             message = f"deleted a file {file.name}",
    #             short_message = "delete_file"
    #         )
    return { "success": True, "detail": "File deleted successfully." }


@router.get("/admin_leads/{file_id}")
async def leads(user: Annotated[User, Depends(get_current_user)],file_id: Optional[int] = None): 
    try:
        filters = {}
        if file_id:
            filters["file_id"] = file_id
       
        leads = await Lead.filter(**filters).all()
        file = await FileModel.filter(id=file_id).first()
        if not file:
            return[]
        return leads
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/leads")
async def leads(user: Annotated[User, Depends(get_current_user)], file_id: Optional[int] = None):
    print("lllll")

    filters = { "file__user_id": user.id , "dnc" : False }
    if file_id:
        filters["file_id"] = file_id
    return await Lead.filter(**filters).all().order_by("id")

@router.get("/leads/{lead_id}")
async def leads(user: Annotated[User, Depends(get_current_user)], lead_id:int):
    print("lead_id", lead_id)
    filters = { "file__user_id": user.id  }
    if lead_id:
        filters["id"] = lead_id
    return await Lead.filter(**filters)

@router.get("/admin/leads")
async def leads(user: Annotated[User, Depends(get_current_user)],file_id: Optional[int] = None, user_id: Optional[int] = None): 
    filters = { "file__user_id": user_id }
    if file_id:
        filters["file_id"] = file_id
    return await Lead.filter(**filters).all()

@router.delete("/leads")
async def delete_lead(data: DeleteLeadPayload, user: Annotated[User, Depends(get_current_user)]):
    leads = await Lead.filter(id__in=data.ids, file__user_id=user.id).all()
    await asyncio.gather(*[lead.delete() for lead in leads])
    return { 
        "success": True, 
        "detail": "Lead(s) deleted successfully." 
    }

@router.get("/all_leads/all_files")
async def get_files(user: Annotated[User, Depends(get_admin)]):
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
            
            file_record = FileModel(name=filename, user=main_admin , url=url, sync_enable= auto_sync, is_syncing =auto_sync,  sync_frequency = sync_frequency  )
            await file_record.save()

            results = await import_leads_csv(content, file_record)
            await Logs.create(
                user = user,
                message = f"imports a file from url : {url}",
                short_message = "import_file"
            )
            return {
                "success": True,
                "results": results,
                "detail": humanize_results(results)
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))




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
            
#             if main_admin.has_active_subscription:
#                 payment_method = await has_payment_method(main_admin)
#                 if payment_method:
#                     return await process_file_upload(content, filename, main_admin, auto_sync, sync_frequency)
#                 else:
#                     raise HTTPException(
#                         status_code=400,
#                         detail="Don't have an active payment method."
#                     )

#             if is_within_trial_period(main_admin.created_at, main_admin.has_free_trial):
#                 num_leads = count_leads_in_csv(content)
                
#                 if num_leads > 2000:
#                     content = "\n".join(content.splitlines()[:2001])  # Limit to 2000 leads
#                     message = "Only 2000 leads will be uploaded due to free trial restrictions."
#                     return await process_file_upload(content, filename, main_admin, auto_sync, sync_frequency, num_leads, message)

#                 return await process_file_upload(content, filename, main_admin, auto_sync, sync_frequency, num_leads)

#             raise HTTPException(
#                 status_code=400,
#                 detail="Your free trial has expired. Please purchase a subscription to continue uploading leads."
#             )

#         except HTTPException as e:
#             raise e
#         except Exception as e:
#             raise HTTPException(
#                 status_code=500,
#                 detail=f"An unexpected error occurred: {str(e)}"
#             )


@router.post("/files/{selectedFile}/overwrite")
async def import_files(url: str, selectedFile: int, user: Annotated[User, Depends(get_current_user)]):
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

            await Logs.create(
                user=user,
                message=f"overwrote file {overwrite_file.name} with data from URL: {url}",
                short_message="overwrite_file"
            )

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

            await Logs.create(
                user=user,
                message=f"appended leads to file {append_file.name} from URL: {url}",
                short_message="append_file"
            )

            return {
                "success": True,
                "results": results,
                "detail": humanize_results(results)
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
   
@router.post("/sync/pause/{id}")
async def syncPause(id : int ,user: Annotated[User, Depends(get_current_user)]):
   try:
        sync = await FileModel.get_or_none(id=id)
        if not sync:
            raise HTTPException(status_code=404, detail="Not found")
        sync.is_syncing= False
        await sync.save()
    
        return {"success" : True , "detail" : "Automatic sync paused" }
   except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
   
@router.post("/sync/resume/{id}")
async def syncResume(id : int ,user: Annotated[User, Depends(get_current_user)]):
    try:
        sync = await FileModel.get_or_none(id=id)
        if not sync:
            raise HTTPException(status_code=404, detail="Not found")
        sync.is_syncing= True
        await sync.save()
    
        return {"success" : True , "detail" : "Automatic sync resumed" }
    except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

@router.get("/sync/status")
async def syncResume():
   return scheduler_status.sync_paused
   

