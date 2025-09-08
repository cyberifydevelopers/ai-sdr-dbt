# import datetime
# from typing import List,Annotated
# from fastapi import Depends, HTTPException,APIRouter
# import httpx
# from pydantic import BaseModel
# from twilio.rest import Client
# from tortoise.transactions import in_transaction
# import os 
# import dotenv

# from helpers.token_helper import get_current_user
# from models.auth import User
# from models.purchased_numbers import PurchasedNumber

# # from helpers.criteria_check import balance_count, has_payment_method,can_process
# from helpers.get_admin import get_admin
# # from helpers.get_current_user import get_current_user
# from helpers.get_user_admin import get_user_admin
# from helpers.vapi_helper import get_headers
# # from models.admin_purchased_number import AdminPurchasedNumber, PeopleGroupPhoneGroupCombinations, PeoplesGroupMember
# # from models.assistant import Assistant
# # from models.defaultSettings import DefaultSettings
# # from models.logs import Logs
# # from models.paymentMethod import PaymentMethod
# # from models.purchased_number import PurchasedNumber
# # from models.spent import Spent
# # from models.user import User
# # from models.vv_adminSetting import VVadminSetting


# dotenv.load_dotenv()
# router = APIRouter()

# class PhoneNumberRequest(BaseModel):
#     area_code: str

# class PurchaseNumberRequest(BaseModel):
#     phone_number: List[str]
# class RemoveNumberRequest(BaseModel):
#     phone_number: str
# class PhoneNumberRequest(BaseModel):
#     country:str
#     area_codes: List[str]  
# class PurchaseNumberRequest(BaseModel):
#     phone_number: List[str]  
    
    

# account_sid = os.environ['TWILIO_ACCOUNT_SID']
# auth_token = os.environ['TWILIO_AUTH_TOKEN']

# print(account_sid)

# client = Client(account_sid, auth_token)


# # @router.post("/number_info")
# # def check_sms_capability(phone_number_sid: str):
# #     try:
# #         phone_number = client.incoming_phone_numbers(phone_number_sid).fetch()
# #         if phone_number.sms_enabled:
# #             return {"sms_capable": True, "phone_number": phone_number.phone_number}
# #         else:
# #             return {"sms_capable": False, "phone_number": phone_number.phone_number}
    
# #     except Exception as e:
# #         return {"error": str(e)}

# #/////////////////////////////////  Available Phone Number /////////////////////////////////////////////
# @router.post("/available_phone_numbers")
# async def buy_phone_number(request: PhoneNumberRequest, user: Annotated[User, Depends(get_current_user)]):
#     available_numbers = []
#     # print(account_sid,auth_token)
#     country = request.country
#     for area_code in request.area_codes:
#         if country == "CA":
#             # Handle Canada
#             numbers_for_area_code = client.available_phone_numbers('CA').local.list(area_code=area_code)
#         else:
#             # Handle United States
#             numbers_for_area_code = client.available_phone_numbers("US").local.list(area_code=area_code)

#         if numbers_for_area_code:
#             for number in numbers_for_area_code:
#                 available_numbers.append({
#                     "friendly_name": number.friendly_name,
#                     "phone_number": number.phone_number,
#                     "region": number.region,
#                     "postal_code": number.postal_code,
#                     "iso_country": number.iso_country,
#                     "capabilities": number.capabilities
#                 })

#     return available_numbers


# #/////////////////////////////////  Purchase Phone Number /////////////////////////////////////////////
# @router.post("/purchase_phone_number")
# async def purchase_phone_number(request: PurchaseNumberRequest, user: Annotated[User, Depends(get_current_user)]):
#     try:
#         user = await User.filter(id=user.id).first()
        
#         # if user.free_trial_start:
          
#             # print("user was start the free trial now check is he with the free trial and also the balance if trial expire")
            
#             # process = await can_process(main_admin.id)

#             # if not process:
#             #     balance = await balance_count(main_admin.id)
#             #     if balance < 5:
#             #         print("Balance is less than 5")
#             #         return {"success": False, "detail": "Insufficient balance."}
            
#             # if process:
#             #     total_number = await PurchasedNumber.filter(user_id=main_admin.id).count()
                
#             #     if total_number >= 1:
#             #         print(f"in free trial and can't but more than one number {total_number}")
#             #         return {
#             #             "success": False,
#             #             "detail": "Can't buy more than one number in the trial period"
#             #         }
#             #     else:
#             #         print(f"purscase number{total_number}")
                        
        
#         # if not user.free_trial_start:
#         # total_number = await PurchasedNumber.filter(user_id=main_admin.id).count()
                
#             # if total_number >= 1:
#             #     print(f"have already a number can't but the other in before or within the trial {total_number}")
#             #     return {
#             #         "success": False,
#             #         "detail": "Can't buy more than one number in the trial period"
#             #     }
                  
        
#         # else:
#             # print("buy number to complete the profile") 
            
#         # payment_method = await has_payment_method(main_admin)
            
#         # if not payment_method:
#         #     return {
#         #         "success": False,
#         #         "detail": "Unable to purchase number. You must have an active payment method first.",
#         #     }
        

#         SMS_URL = os.getenv("SMS_URL")
#         async with in_transaction():
#             purchased_numbers = []
#             for phone_number in request.phone_number:
#                 purchased_number = client.incoming_phone_numbers.create(
#                     phone_number=phone_number
#                 )
#                 client.incoming_phone_numbers(purchased_number.sid).update(
#                     sms_url=SMS_URL
#                 )
#                 print(f"numner {purchased_number}")
#                 attach_payload = {
#                     "provider": "twilio",
#                     "number": purchased_number.phone_number,
#                     "twilioAccountSid": os.environ.get('TWILIO_ACCOUNT_SID'),
#                     "twilioAuthToken": os.environ.get('TWILIO_AUTH_TOKEN'),
#                     "name": "Twilio Number",
#                 }
              
#                 attach_url = os.environ.get('VAPI_ATTACH_PHONE_URL')
#                 if not attach_url:
#                     raise HTTPException(status_code=500, detail="Attachment URL is not configured.")
                
#                 async with httpx.AsyncClient() as vapiclient:
#                     attach_response = await vapiclient.post(attach_url, json=attach_payload, headers=get_headers() )
#                     attach_data = attach_response.json()
#                     print(attach_data)
#                     if attach_response.status_code in [200, 201]:
#                         vapi_phone_uuid = attach_data.get("id")
#                         purchased_entry = await PurchasedNumber.create(
#                             user=user,
#                             phone_number=purchased_number.phone_number,
#                             vapi_phone_uuid=vapi_phone_uuid,
#                             friendly_name=purchased_number.friendly_name,
#                             region=None, 
#                             postal_code=None,
#                             iso_country=None,
#                         )
#                         purchased_numbers.append(purchased_entry.phone_number)
            
#             # user_setting = await DefaultSettings.first()
#             # main_admin = await User.filter(company_id=user.company_id, main_admin=True, role="company_admin").first()

#             # await Spent.create(
#             #     user=main_admin,
#             #     spent_money=user_setting.phone_number_price,
#             #     description="Purchased a phone number"
#             # )

#             # await Logs.create(
#             #     user=user,
#             #     message=f"Purchased phone numbers: {', '.join(purchased_numbers)}",
#             #     short_message="purchase_number"
#             # )
            
#             return {
#                 "success": True,
#                 "detail": f"Phone numbers {', '.join(purchased_numbers)} purchased and saved successfully!",
#                 "purchased_numbers": purchased_numbers,
#                 "sendedNumber":request.phone_number
#             }

#     except Exception as e:
#         error_message = str(e) 
#         raise HTTPException(status_code=400, detail={"error": error_message})

# #/////////////////////////////////  Get Purchased Phone Numbers ///////////////////////////////
# @router.get("/purchased_numbers")
# async def get_purchased_numbers( user: Annotated[User, Depends(get_current_user)],
# ):
#     purchased_numbers = await PurchasedNumber.filter(user=user).all().order_by("id")
    
#     if not purchased_numbers:
#         return {"message": "No purchased numbers found.", "purchased_numbers": []}

#     return [
#         {
#             "phone_number": pn.phone_number,
#             "friendly_name": pn.friendly_name,
#             "date_purchased": pn.created_at,
#             "user": {
#                 "username": user.name,
#                 "email": user.email
#             },
#             "attached_assistant" : pn.attached_assistant
#         }
#         for pn in purchased_numbers
#     ]
# # @router.get("/vv-admin-numbers")
# # async def vv_admin_numbers(
# #     user: Annotated[User, Depends(get_current_user)],
# #     main_admin: Annotated[User, Depends(get_user_admin)]
# # ):
# #     print("user name", user.name)
# #     user_membership = await PeoplesGroupMember.filter(user=main_admin).first()
    
# #     if not user_membership:
# #         return []  
    
# #     people_group_id = user_membership.peoples_group_id
# #     print("people_group_id", people_group_id)
# #     if not people_group_id:
# #         return []  
    
# #     combination = await PeopleGroupPhoneGroupCombinations.filter(
# #         peoples_group_id=people_group_id
# #     ).first()
    
# #     if not combination:
# #         return []  
    
# #     admin_numbers_group_id = combination.admin_numbers_group_id
    
# #     if not admin_numbers_group_id:
# #         return []
    
# #     purchased_numbers = await AdminPurchasedNumber.filter(
# #         group_id=admin_numbers_group_id
# #     ).order_by("id")
    
# #     if not purchased_numbers:
# #         return []
    
# #     result = []
    
# #     for pn in purchased_numbers:
# #         assistant = await Assistant.filter(user = main_admin ,attached_Number=pn.phone_number).first()
        
# #         assistant_id = assistant.id if assistant else None
# #         print("assistant_id",assistant_id)
# #         result.append({
# #             "phone_number": pn.phone_number,
# #             "friendly_name": pn.friendly_name,
# #             "date_purchased": pn.created_at,
# #             "attached_assistant": assistant_id
# #         })
    
# #     return result

# # @router.get("/get-purchased-and-vv-numbers")
# # async def get_purchased_and_vv_numbers(
# #     user: Annotated[User, Depends(get_current_user)],
# #     main_admin: Annotated[User, Depends(get_user_admin)]
# # ):
# #     purchased_numbers = await PurchasedNumber.filter(user=main_admin).all().order_by("id")
    
# #     vv_admin_numbers = []
    
# #     user_membership = await PeoplesGroupMember.filter(user=main_admin).first()
    
# #     if user_membership:
# #         people_group_id = user_membership.peoples_group_id
# #         if people_group_id:
# #             combination = await PeopleGroupPhoneGroupCombinations.filter(
# #                 peoples_group_id=people_group_id
# #             ).first()
            
# #             if combination and combination.admin_numbers_group_id:
# #                 vv_admin_numbers = await AdminPurchasedNumber.filter(
# #                     group_id=combination.admin_numbers_group_id
# #                 ).order_by("id")
    
# #     combined_numbers = []
    
# #     for pn in purchased_numbers:
# #         assistant = await Assistant.filter(user = main_admin , attached_Number=pn.phone_number).first()
# #         assistant_id = assistant.id if assistant else None
        
# #         combined_numbers.append({
# #             "phone_number": pn.phone_number,
# #             "friendly_name": pn.friendly_name,
# #             "date_purchased": pn.created_at,
# #             "user": {
# #                 "username": user.name,
# #                 "email": user.email
# #             },
# #             "attached_assistant": assistant_id,  
# #             "number_type": "purchased"
# #         })
    
# #     for pn in vv_admin_numbers:
# #         assistant = await Assistant.filter(user = main_admin , attached_Number=pn.phone_number).first()
# #         assistant_id = assistant.id if assistant else None
        
# #         combined_numbers.append({
# #             "phone_number": pn.phone_number,
# #             "friendly_name": pn.friendly_name,
# #             "date_purchased": pn.created_at,
# #             "user": {
# #                 "username": "VV Admin",
# #                 "email": ""
# #             },
# #             "attached_assistant": assistant_id, 
# #             "number_type": "vv_admin"
# #         })
    
# #     return combined_numbers

# #/////////////////////////////////  Remove/Return Phone Number //////////////////////////////////////////
# @router.post("/remove-phone-number")
# async def return_phone_number(request: RemoveNumberRequest, user: Annotated[User, Depends(get_current_user)]):
#     try:
#         purchased_number = client.incoming_phone_numbers.list(phone_number=request.phone_number)
        
#         if not purchased_number:
#            return {
#            "success": False,
#            "detail": f"Phone number {request.phone_number} was not found or has already been returned."
#                 }
#         number_to_return = purchased_number[0]

#         number_to_return.delete()
        
#         number = await PurchasedNumber.filter(phone_number=request.phone_number).first()

#         async with httpx.AsyncClient() as vapiclient:
#             attach_url = f"{os.environ.get('VAPI_ATTACH_PHONE_URL')}/{number.vapi_phone_uuid}"
#             attach_response = await vapiclient.delete(attach_url, headers=get_headers() )

#         await PurchasedNumber.filter(phone_number=number.phone_number).delete()

#         return {
#             "success": True,
#             "detail": f"Phone number {number.phone_number} has been returned successfully!"
#         }

#     except Exception as e:
#         error_message = str(e)
#         raise HTTPException(status_code=400, detail={"error": error_message})






# # @router.get("/phone_numbers")
# # async def get_purchased_numbers(user: Annotated[User, Depends(get_admin)]):
# #     purchased_numbers = await PurchasedNumber.all().prefetch_related("user__company")  # Prefetching company data

# #     if not purchased_numbers:
# #         return {"message": "No purchased numbers found."}

# #     return [
# #         {
# #             **dict(pn),
# #             "phone_number": pn.phone_number,
# #             "username": pn.user.name if pn.user else None,
# #             "email": pn.user.email if pn.user else None,
# #             "company_name": pn.user.company.company_name if pn.user and pn.user.company else None  
# #         }
# #         for pn in purchased_numbers
# #     ]



































import datetime
from typing import List, Annotated, Optional, Tuple
from fastapi import Depends, HTTPException, APIRouter
import httpx
from pydantic import BaseModel, Field, ConfigDict
from twilio.rest import Client
from tortoise.transactions import in_transaction
import os
import dotenv

from helpers.token_helper import get_current_user
from models.auth import User
from models.purchased_numbers import PurchasedNumber
from helpers.vapi_helper import get_headers

dotenv.load_dotenv()
router = APIRouter()

# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class TwilioCredentialsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    account_sid: str = Field(..., description="User's Twilio Account SID")
    auth_token: str = Field(..., description="User's Twilio Auth Token")
    validate_credentials: bool = Field(
        True, alias="validate",
        description="If true, verify credentials with Twilio before saving",
    )

class PhoneNumberRequest(BaseModel):
    # Accepts 'US', 'USA', 'United States', 'CA', 'Canada'
    country: str
    area_codes: List[str]

class PurchaseNumberRequest(BaseModel):
    phone_number: List[str]

class RemoveNumberRequest(BaseModel):
    phone_number: str

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_country(country: str) -> str:
    c = (country or "").strip().upper()
    if c in {"US", "USA", "UNITED STATES", "UNITED-STATES", "UNITED STATES OF AMERICA"}:
        return "US"
    if c in {"CA", "CANADA"}:
        return "CA"
    raise HTTPException(status_code=400, detail="country must be US or CA")

def _twilio_client_from_values(account_sid: Optional[str], auth_token: Optional[str]) -> Tuple[Client, str, str]:
    sid = account_sid or os.environ.get("TWILIO_ACCOUNT_SID")
    token = auth_token or os.environ.get("TWILIO_AUTH_TOKEN")
    if not sid or not token:
        raise HTTPException(
            status_code=400,
            detail="No Twilio credentials found for this user. Set them via POST /twilio/credentials.",
        )
    return Client(sid, token), sid, token

def _twilio_client_for_user_sync(user: User) -> Tuple[Client, str, str]:
    # Synchronous helper that reads attributes already present on the instance
    return _twilio_client_from_values(
        getattr(user, "twilio_account_sid", None),
        getattr(user, "twilio_auth_token", None),
    )

async def _validate_twilio_credentials(account_sid: str, auth_token: str) -> None:
    try:
        client = Client(account_sid, auth_token)
        client.api.accounts(account_sid).fetch()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid Twilio credentials: {str(e)}")

# ─────────────────────────────────────────────────────────────────────────────
# Credentials
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/twilio/credentials")
@router.put("/twilio/credentials")
async def upsert_twilio_credentials(
    payload: TwilioCredentialsRequest,
    user: Annotated[User, Depends(get_current_user)],
):
    if payload.validate_credentials:
        await _validate_twilio_credentials(payload.account_sid, payload.auth_token)

    # ✅ Update by query to avoid stale instance issues
    updated = await User.filter(id=user.id).update(
        twilio_account_sid=payload.account_sid,
        twilio_auth_token=payload.auth_token,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="User not found.")

    return {
        "success": True,
        "detail": "Twilio credentials saved for this user.",
        "masked": {
            "account_sid": f"{payload.account_sid[:4]}****{payload.account_sid[-4:]}",
            "auth_token": f"{payload.auth_token[:2]}****{payload.auth_token[-2:]}",
        },
    }

@router.get("/twilio/credentials")
async def get_twilio_credentials_masked(
    user: Annotated[User, Depends(get_current_user)],
):
    # ✅ Reload from DB to ensure we see current values
    db_user = await User.get(id=user.id)
    sid = getattr(db_user, "twilio_account_sid", None)
    token = getattr(db_user, "twilio_auth_token", None)

    if not sid or not token:
        raise HTTPException(status_code=404, detail="No Twilio credentials set for this user.")

    return {
        "account_sid": f"{sid[:4]}****{sid[-4:]}",
        "auth_token": f"{token[:2]}****{token[-2:]}",
    }

# ─────────────────────────────────────────────────────────────────────────────
# Numbers: Search / Purchase / List / Remove
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/available_phone_numbers")
async def available_phone_numbers(
    request: PhoneNumberRequest,
    user: Annotated[User, Depends(get_current_user)],
):
    db_user = await User.get(id=user.id)  # ✅ ensure fresh fields
    client, _, _ = _twilio_client_for_user_sync(db_user)

    country = _normalize_country(request.country)
    available_numbers: List[dict] = []

    for area_code in request.area_codes:
        area_code = (area_code or "").strip()
        if not area_code.isdigit() or len(area_code) != 3:
            raise HTTPException(status_code=400, detail=f"Invalid area code: {area_code}")

        numbers_for_area_code = client.available_phone_numbers(country).local.list(area_code=area_code)

        for number in numbers_for_area_code or []:
            available_numbers.append(
                {
                    "friendly_name": number.friendly_name,
                    "phone_number": number.phone_number,
                    "region": getattr(number, "region", None),
                    "postal_code": getattr(number, "postal_code", None),
                    "iso_country": getattr(number, "iso_country", None),
                    "capabilities": getattr(number, "capabilities", None),
                }
            )

    return available_numbers

@router.post("/purchase_phone_number")
async def purchase_phone_number(
    request: PurchaseNumberRequest,
    user: Annotated[User, Depends(get_current_user)],
):
    """
    Purchases numbers using the *user's* Twilio credentials and attaches each to Vapi.
    """
    try:
        db_user = await User.get(id=user.id)  # ✅ fresh from DB
        client, user_sid, user_token = _twilio_client_for_user_sync(db_user)
        SMS_URL = os.getenv("SMS_URL")

        async with in_transaction():
            purchased_numbers: List[str] = []

            for phone_number in request.phone_number:
                purchased_number = client.incoming_phone_numbers.create(phone_number=phone_number)

                if SMS_URL:
                    client.incoming_phone_numbers(purchased_number.sid).update(sms_url=SMS_URL)

                attach_payload = {
                    "provider": "twilio",
                    "number": purchased_number.phone_number,
                    "twilioAccountSid": user_sid,
                    "twilioAuthToken": user_token,
                    "name": "Twilio Number",
                }

                attach_url = os.environ.get("VAPI_ATTACH_PHONE_URL")
                if not attach_url:
                    try:
                        client.incoming_phone_numbers(purchased_number.sid).delete()
                    except Exception:
                        pass
                    raise HTTPException(status_code=500, detail="VAPI_ATTACH_PHONE_URL is not configured.")

                async with httpx.AsyncClient() as vapiclient:
                    attach_response = await vapiclient.post(attach_url, json=attach_payload, headers=get_headers())
                    if attach_response.status_code not in (200, 201):
                        try:
                            client.incoming_phone_numbers(purchased_number.sid).delete()
                        except Exception:
                            pass
                        raise HTTPException(
                            status_code=attach_response.status_code,
                            detail=f"Vapi attach failed: {attach_response.text}",
                        )

                    attach_data = attach_response.json()
                    vapi_phone_uuid = attach_data.get("id")

                await PurchasedNumber.create(
                    user=db_user,
                    phone_number=purchased_number.phone_number,
                    vapi_phone_uuid=vapi_phone_uuid,
                    friendly_name=purchased_number.friendly_name,
                    region=None,
                    postal_code=None,
                    iso_country=None,
                )

                purchased_numbers.append(purchased_number.phone_number)

        return {
            "success": True,
            "detail": f"Phone numbers {', '.join(purchased_numbers)} purchased and saved successfully!",
            "purchased_numbers": purchased_numbers,
            "sentNumbers": request.phone_number,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})

@router.get("/purchased_numbers")
async def get_purchased_numbers(
    user: Annotated[User, Depends(get_current_user)],
):
    db_user = await User.get(id=user.id)
    purchased_numbers = await PurchasedNumber.filter(user=db_user).all().order_by("id")

    if not purchased_numbers:
        return {"message": "No purchased numbers found.", "purchased_numbers": []}

    return [
        {
            "phone_number": pn.phone_number,
            "friendly_name": pn.friendly_name,
            "date_purchased": pn.created_at,
            "user": {"username": db_user.name, "email": db_user.email},
            "attached_assistant": pn.attached_assistant,
        }
        for pn in purchased_numbers
    ]

@router.post("/remove-phone-number")
async def return_phone_number(
    request: RemoveNumberRequest,
    user: Annotated[User, Depends(get_current_user)],
):
    try:
        db_user = await User.get(id=user.id)  # ✅ fresh
        client, _, _ = _twilio_client_for_user_sync(db_user)

        matches = client.incoming_phone_numbers.list(phone_number=request.phone_number)
        if not matches:
            return {
                "success": False,
                "detail": f"Phone number {request.phone_number} was not found or has already been returned.",
            }

        to_return = matches[0]
        to_return.delete()

        number_row = await PurchasedNumber.filter(phone_number=request.phone_number, user=db_user).first()
        if number_row:
            if number_row.vapi_phone_uuid:
                attach_url_base = os.environ.get("VAPI_ATTACH_PHONE_URL")
                if attach_url_base:
                    async with httpx.AsyncClient() as vapiclient:
                        delete_url = f"{attach_url_base}/{number_row.vapi_phone_uuid}"
                        await vapiclient.delete(delete_url, headers=get_headers())

            await PurchasedNumber.filter(id=number_row.id).delete()

        return {"success": True, "detail": f"Phone number {request.phone_number} has been returned successfully!"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})
