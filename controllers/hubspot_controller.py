# from fastapi import APIRouter, HTTPException, Depends
# from typing import List, Dict, Any
# import os
# import requests
# from helpers.token_helper import get_current_user
# from models.auth import User
# from typing import Annotated

# router = APIRouter()

# @router.get("/hubspot/contacts")
# async def get_hubspot_contacts(user: Annotated[User, Depends(get_current_user)]):
#     """
#     Fetch all contacts from HubSpot using the HUBSPOT_ACCESS_TOKEN
#     """
#     try:
#         # Get the HubSpot access token from environment variables
#         hubspot_token = os.getenv("HUBSPOT_ACCESS_TOKEN")
        
#         if not hubspot_token:
#             raise HTTPException(
#                 status_code=500, 
#                 detail="HUBSPOT_ACCESS_TOKEN not configured in environment variables"
#             )
        
#         # HubSpot API endpoint for contacts
#         url = "https://api.hubapi.com/crm/v3/objects/contacts"
        
#         # Headers for HubSpot API
#         headers = {
#             "Authorization": f"Bearer {hubspot_token}",
#             "Content-Type": "application/json"
#         }
        
#         # Parameters to get all contacts (you can adjust these as needed)
#         params = {
#             "limit": 100,  # Number of contacts per request
#             "properties": "firstname,lastname,email,phone,company,lifecyclestage,createdate,lastmodifieddate"
#         }
        
#         # Make the API request
#         response = requests.get(url, headers=headers, params=params)
        
#         # Check if the request was successful
#         if response.status_code == 200:
#             data = response.json()
#             contacts = data.get("results", [])
            
#             # If there are more contacts, you might want to implement pagination
#             # For now, we'll return the first 100 contacts
            
#             return {
#                 "success": True,
#                 "message": f"Successfully fetched {len(contacts)} contacts from HubSpot",
#                 "data": {
#                     "contacts": contacts,
#                     "total_count": len(contacts),
#                     "paging": data.get("paging", {})
#                 }
#             }
#         else:
#             # Handle different error status codes
#             error_message = f"HubSpot API error: {response.status_code}"
#             try:
#                 error_data = response.json()
#                 error_message = error_data.get("message", error_message)
#             except:
#                 pass
                
#             raise HTTPException(
#                 status_code=response.status_code,
#                 detail=error_message
#             )
            
#     except requests.exceptions.RequestException as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Error connecting to HubSpot API: {str(e)}"
#         )
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Unexpected error: {str(e)}"
#         )



from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Dict, Any, Optional
import os
import httpx
from helpers.token_helper import get_current_user
from models.auth import User

router = APIRouter()

HUBSPOT_BASE = "https://api.hubapi.com"
CONTACT_PROPS = [
    "firstname",
    "lastname",
    "email",
    "phone",
    "company",
    "lifecyclestage",
    "createdate",
    "lastmodifieddate",
]

def _pick_token(user: User) -> Optional[str]:
    # If you store per-user tokens, prefer that (adjust attr name accordingly)
    user_token = getattr(user, "hubspot_access_token", None)
    if user_token:
        return user_token
    # Fallback to env for single-tenant/ops usage
    return os.getenv("HUBSPOT_ACCESS_TOKEN")

@router.get("/hubspot/contacts")
async def get_hubspot_contacts(
    user: User = Depends(get_current_user),
    limit: int = Query(100, ge=1, le=100),
    after: Optional[str] = Query(None, description="HubSpot paging cursor"),
    fetch_all: bool = Query(False, description="Fetch all pages until exhausted")
):
    """
    Fetch HubSpot contacts (paginated). 
    - By default returns up to `limit` (max 100).
    - Pass `after` to get subsequent pages.
    - Set `fetch_all=true` to auto-paginate all contacts.
    """
    token = _pick_token(user)
    if not token:
        raise HTTPException(500, "HubSpot token not configured (user or env).")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    async def fetch_page(client: httpx.AsyncClient, after_cursor: Optional[str]):
        params: Dict[str, Any] = {
            "limit": limit,
            "archived": "false",
            # passing list -> httpx encodes as repeated 'properties=' keys (preferred by HubSpot)
            "properties": CONTACT_PROPS,
        }
        if after_cursor:
            params["after"] = after_cursor

        resp = await client.get(f"{HUBSPOT_BASE}/crm/v3/objects/contacts", headers=headers, params=params, timeout=30.0)
        # Handle typical errors cleanly
        if resp.status_code == 401:
            raise HTTPException(401, "Unauthorized: invalid/expired HubSpot token or missing scopes.")
        if resp.status_code == 403:
            raise HTTPException(403, "Forbidden: token lacks required scopes (need crm.objects.contacts.read).")
        if resp.status_code == 429:
            raise HTTPException(429, "Rate limited by HubSpot. Please retry later.")

        if not resp.is_success:
            try:
                j = resp.json()
                msg = j.get("message") or j.get("reason") or str(j)
            except Exception:
                msg = resp.text
            raise HTTPException(resp.status_code, f"HubSpot API error: {msg}")

        return resp.json()

    results: List[Dict[str, Any]] = []
    next_after = after
    async with httpx.AsyncClient() as client:
        if fetch_all:
            # keep pulling pages until no 'paging.next.after'
            while True:
                j = await fetch_page(client, next_after)
                results.extend(j.get("results", []))
                next_info = j.get("paging", {}).get("next", {})
                next_after = next_info.get("after")
                if not next_after:
                    break
            return {
                "success": True,
                "message": f"Fetched {len(results)} contacts from HubSpot",
                "data": {
                    "contacts": results,
                    "total_count": len(results),
                    "paging": {"next": None},
                },
            }
        else:
            j = await fetch_page(client, next_after)
            contacts = j.get("results", [])
            paging = j.get("paging", {})
            return {
                "success": True,
                "message": f"Fetched {len(contacts)} contacts from HubSpot",
                "data": {
                    "contacts": contacts,
                    "total_count": len(contacts),
                    "paging": paging,  # contains next.after if more pages exist
                },
            }
