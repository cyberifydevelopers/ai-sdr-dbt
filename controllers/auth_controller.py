
# from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Request
# from argon2 import PasswordHasher
# from pydantic import BaseModel, EmailStr
# from typing import Annotated, Optional
# from models.auth import User, Code
# from helpers.email_helper import generate_code
# from helpers.email_generator import confirmation_email
# from helpers.token_helper import generate_user_token, get_current_user

# # >>> NEW: imports for profile photo handling
# import os
# import uuid
# from pathlib import Path
# from starlette.responses import RedirectResponse

# auth_router = APIRouter()
# ph = PasswordHasher()

# # >>> NEW: basic config for storing profile photos
# PROFILE_PHOTO_STORAGE = os.getenv("PROFILE_PHOTO_STORAGE", "media/profile_photos")
# PROFILE_PHOTO_URL_PATH = os.getenv("PROFILE_PHOTO_URL_PATH", "/media/profile_photos")
# ALLOWED_IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}
# MAX_PROFILE_PHOTO_BYTES = 5 * 1024 * 1024  # 5 MB
# Path(PROFILE_PHOTO_STORAGE).mkdir(parents=True, exist_ok=True)

# def _ext_from_content_type(content_type: str) -> str:
#     return {
#         "image/png": ".png",
#         "image/jpeg": ".jpg",
#         "image/webp": ".webp",
#     }.get(content_type, "")

# def _abs_url(request: Request, path: str) -> str:
#     base = str(request.base_url).rstrip("/")
#     rel = "/" + path.lstrip("/")
#     return f"{base}{rel}"

# # ////////////////////////////  Schemas  /////////////////////////////////////////////////

# class SignupPayload(BaseModel):
#     name: str
#     email: EmailStr
#     password: str

# class LoginPayload(BaseModel):
#     email: str
#     password: str

# class AccountVerificationPayload(BaseModel):
#     email: EmailStr
#     code: int

# class PasswordResetCode(BaseModel):
#     email: EmailStr

# class VerifyCodePayload(BaseModel):
#     email: EmailStr
#     code: str
    
# class ResetCodePayload(BaseModel):
#     email: EmailStr
#     code: str
#     password: str
    
# class UpdateProfilePayload(BaseModel):
#     email: Optional[EmailStr] = None
#     name: Optional[str] = None
#     password: Optional[str] = None



# # --- put near other Pydantic schemas in your auth controller ---
# from datetime import datetime
# from pydantic import BaseModel, Field
# from typing import Optional

# class ConsentPayload(BaseModel):
#     has_consent: bool = Field(..., description="True/False: do you have consent to call these leads?")
#     note: Optional[str] = Field(
#         default=None,
#         description="Optional description (e.g., how consent was obtained, list source)"
#     )

# class ConsentOut(BaseModel):
#     has_consent: bool
#     note: Optional[str] = None
#     updated_at: Optional[datetime] = None

# # ////////////////////////////  Sign up  /////////////////////////////////////////////////
# @auth_router.post('/signup')
# async def signup(payload: SignupPayload):
#     user = await User.filter(email=payload.email).first()
#     if user: 
#         raise HTTPException(status_code=400, detail="User already exists")
#     try:
#         user = User(
#             name=payload.name,
#             email=payload.email,
#             password=ph.hash(payload.password),
#         )
#         await user.save()
#         is_email_sent: bool = await generate_code("account_activation", user=user)
#         if is_email_sent:
#             return {"success": True, "verify": False, "detail": "Verification Email sent successfully"}
#         else:
#             await user.delete()
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=f"server error {e}")

# # ////////////////////////////  Sign in  /////////////////////////////////////////////////
# @auth_router.post("/signin")
# async def signin(data: LoginPayload):
#     user = await User.filter(email=data.email).first()
#     if not user:
#         raise HTTPException(status_code=400, detail="User Not found")
#     try:
#         is_varified = ph.verify(user.password, data.password)
#     except:
#         raise HTTPException(status_code=400, detail="Invalid Credentials.")
    
#     if user.email_verified is False:
#         is_email_sent: bool = await generate_code("account_activation", user=user)
#         if is_email_sent:
#             return {"success": True, "verify": False, "detail": "Email not verified, code sent"}
#         else:
#             raise HTTPException(status_code=400, detail="Email not verified, code not sent")
#     try:
#         token = generate_user_token({"id": user.id})
#         return {
#             "success": True,
#             "token": token,
#             "user": {
#                 'name': user.name,
#                 'email': user.email,
#                 'user_id': user.id,
#                 'role': user.role
#             },
#             "detail": "Login Successfully"
#         }
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=str(e))

# # ////////////////////////////  Delete Acccount  /////////////////////////////////////////////////
# @auth_router.delete("/delete-account")
# async def delete_account(user: Annotated[User, Depends(get_current_user)]):
#     try:
#         await user.delete()
#         return {"success": True, "detail": "Account deleted successfully"}
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=str(e))

# # ////////////////////////////  Account Verification  ////////////////////////////
# @auth_router.post("/account-verification")
# async def account_verification(payload: AccountVerificationPayload):
#     user = await User.filter(email=payload.email).first()
#     if not user:
#         raise HTTPException(status_code=400, detail="User not found")
#     code = await Code.filter(user__id=user.id).order_by("-id").first()
#     if not code:
#         raise HTTPException(detail="Invalid code", status_code=400)
#     try:
#         if code.value == str(payload.code):
#             user.email_verified = True
#             await user.save()
#             confirmation_email(to_email=user.email)
#             await code.delete()
#             token = generate_user_token({"id": user.id})
#             return {
#                 "success": True,
#                 "token": token,
#                 "user": {'name': user.name, 'email': user.email},
#                 "detail": "Account verified successfully"
#             }
#         else:
#             raise HTTPException(detail="Invalid code", status_code=400)
#     except Exception:
#         raise HTTPException(detail="Invalid code", status_code=400)

# # ////////////////////////////  Resend OTP  /////////////////////////////////////////////////
# @auth_router.post("/resend-otp")
# async def resend_otp(payload: PasswordResetCode):
#     user = await User.filter(email=payload.email).first()
#     if not user:
#         raise HTTPException(detail="Account not found", status_code=400)
#     try:
#         await generate_code("account_activation", user)
#         return {"success": True, "detail": "Account activation code sent successfully"}
#     except Exception as e:
#         raise HTTPException(detail=str(e), status_code=500)

# # ////////////////////////////  Password Reset Code  /////////////////////////////////////
# @auth_router.post("/password-reset-code")
# async def password_reset_code(payload: PasswordResetCode):
#     user = await User.filter(email=payload.email).first()
#     if not user:
#         raise HTTPException(detail="Account not found", status_code=400)
#     try:
#         await generate_code("password_reset", user)
#         return {"success": True, "detail": "Password reset code sent successfully"}
#     except Exception as e:
#         raise HTTPException(detail=str(e), status_code=500)

# # ////////////////////////////  Confirm OTP  /////////////////////////////////////////////////
# @auth_router.post("/confirm-otp")
# async def confirm_otp(payload: VerifyCodePayload):
#     user = await User.filter(email=payload.email).first()
#     if not user:
#         raise HTTPException(detail="User not found", status_code=400)
#     code = await Code.filter(user__id=user.id, type="password_reset").order_by("-id").first()
#     if payload.code == code.value:
#         return {"success": True, "detail": "Otp verified successfully"}
#     else:
#         raise HTTPException(detail="Invalid code", status_code=400)

# # ////////////////////////////  Validate Token  /////////////////////////////////////////////////
# @auth_router.get("/validate-token")
# async def validate_token(user: Annotated[User, Depends(get_current_user)]):
#     if not user:
#         raise HTTPException(detail="Un Authenticated", status_code=401)
#     return {"success": True, "detail": "Token verified successfully"}

# # ////////////////////////////  Reset Password  /////////////////////////////////////////////////
# @auth_router.post("/reset-password")
# async def reset_password(payload: ResetCodePayload):
#     try:
#         user = await User.filter(email=payload.email).first()
#         if user:
#             code = await Code.filter(user__id=user.id, type="password_reset").order_by("-id").first()
#             if payload.code == code.value:
#                 user.password = ph.hash(payload.password)
#                 await user.save()
#                 await code.delete()
#                 return {"success": True, "detail": "Password reset successfully"}
#             else:
#                 raise HTTPException(detail="Invalid code", status_code=400)
#         else:
#             raise HTTPException(detail="User not found", status_code=400)
#     except Exception as e:
#         raise HTTPException(detail=str(e), status_code=400)

# # ////////////////////////////  Update Profile  /////////////////////////////////////////////////
# @auth_router.post("/update-profile")
# async def update_profile(data: UpdateProfilePayload, user: Annotated[User, Depends(get_current_user)]):
#     if data.email:
#         if await User.filter(email=data.email).first():
#             if data.email != user.email:
#                 raise HTTPException(detail="Email already exists", status_code=400)
#     if data.password:
#         try:
#             ph.verify(user.password, data.password)
#         except:
#             raise HTTPException(status_code=403, detail="Current password is incorrect")
#     try:
#         if data.password:
#             user.password = ph.hash(data.password)
#         if data.name:
#             user.name = data.name
#         if data.email:
#             user.email = data.email
#         await user.save()
#         return {
#             "success": True,
#             "data": {"name": user.name, "email": user.email},
#             "detail": "Profile updated successfully"
#         }
#     except Exception as e:
#         raise HTTPException(detail=str(e), status_code=400)

# # ////////////////////////////  Profile Photo APIs  /////////////////////////////////////////////////

# @auth_router.post("/profile-photo")
# async def upload_profile_photo(
#     request: Request,
#     file: UploadFile = File(...),
#     user: Annotated[User, Depends(get_current_user)] = None,
# ):
#     if file.content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
#         raise HTTPException(status_code=400, detail=f"Unsupported type. Allowed: {', '.join(ALLOWED_IMAGE_CONTENT_TYPES)}")
#     content = await file.read()
#     if len(content) > MAX_PROFILE_PHOTO_BYTES:
#         raise HTTPException(status_code=400, detail=f"Image too large. Max {MAX_PROFILE_PHOTO_BYTES // (1024*1024)} MB")
#     ext = _ext_from_content_type(file.content_type)
#     new_filename = f"{uuid.uuid4().hex}{ext}"
#     new_path = Path(PROFILE_PHOTO_STORAGE) / new_filename
#     with open(new_path, "wb") as f:
#         f.write(content)
#     # delete old
#     if user.profile_photo:
#         try:
#             old_file = Path(".") / user.profile_photo.lstrip("/")
#             if not old_file.exists():
#                 old_file = Path(PROFILE_PHOTO_STORAGE) / Path(user.profile_photo).name
#             if old_file.exists():
#                 old_file.unlink()
#         except Exception:
#             pass
#     rel_url = f"{PROFILE_PHOTO_URL_PATH}/{new_filename}".replace("//", "/")
#     user.profile_photo = rel_url
#     await user.save()
#     return {"success": True, "detail": "Uploaded successfully", "photo_url": _abs_url(request, rel_url)}

# @auth_router.get("/profile-photo")
# async def get_profile_photo(request: Request, redirect: Optional[bool] = False, user: Annotated[User, Depends(get_current_user)] = None):
#     if not user.profile_photo:
#         raise HTTPException(status_code=404, detail="No profile photo set")
#     abs_url = _abs_url(request, user.profile_photo)
#     if redirect:
#         return RedirectResponse(url=abs_url)
#     return {"success": True, "photo_url": abs_url}

# @auth_router.delete("/profile-photo")
# async def delete_profile_photo(user: Annotated[User, Depends(get_current_user)]):
#     if not user.profile_photo:
#         raise HTTPException(status_code=404, detail="No profile photo to delete")
#     try:
#         stored = str(user.profile_photo).lstrip("/")
#         abs_path = Path(".") / stored
#         if not abs_path.exists():
#             abs_path = Path(PROFILE_PHOTO_STORAGE) / Path(stored).name
#         if abs_path.exists():
#             abs_path.unlink()
#     except Exception:
#         pass
#     user.profile_photo = None
#     await user.save()
#     return {"success": True, "detail": "Profile photo deleted successfully"}

# # ////////////////////////////  Get User info  /////////////////////////////////////////////////
# @auth_router.get("/user-info")
# async def get_user_info(request: Request, user: Annotated[User, Depends(get_current_user)]):
#     rel = user.profile_photo
#     abs_url = _abs_url(request, rel) if rel else None
#     return {
#         "success": True,
#         "data": {
#             "name": user.name,
#             "email": user.email,
#             "role": getattr(user, "role", None),
#             "profile_photo": rel,
#             "profile_photo_url": abs_url,
#         }
#     }

# # ////////////////////////////  Change Password  /////////////////////////////////////////////////

# class ChangePasswordPayload(BaseModel):
#     old_password: str
#     new_password: str

# @auth_router.post("/change-password")
# async def change_password(payload: ChangePasswordPayload, user: Annotated[User, Depends(get_current_user)]):
#     try:
#         try:
#             ph.verify(user.password, payload.old_password)
#         except:
#             raise HTTPException(status_code=400, detail="Current password is incorrect")
#         user.password = ph.hash(payload.new_password)
#         await user.save()
#         return {"success": True, "detail": "Password changed successfully"}
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error changing password: {str(e)}")




# controllers/auth_controller.py

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Request
from argon2 import PasswordHasher
from pydantic import BaseModel, EmailStr, Field
from typing import Annotated, Optional
from datetime import datetime
from pathlib import Path
import os
import uuid
from starlette.responses import RedirectResponse

from models.auth import User, Code
from helpers.email_helper import generate_code
from helpers.email_generator import confirmation_email
from helpers.token_helper import generate_user_token, get_current_user

auth_router = APIRouter()
ph = PasswordHasher()

# ------------------------------ Profile Photos -------------------------------

PROFILE_PHOTO_STORAGE = os.getenv("PROFILE_PHOTO_STORAGE", "media/profile_photos")
PROFILE_PHOTO_URL_PATH = os.getenv("PROFILE_PHOTO_URL_PATH", "/media/profile_photos")
ALLOWED_IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_PROFILE_PHOTO_BYTES = 5 * 1024 * 1024  # 5 MB
Path(PROFILE_PHOTO_STORAGE).mkdir(parents=True, exist_ok=True)

def _ext_from_content_type(content_type: str) -> str:
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
    }.get(content_type, "")

def _abs_url(request: Request, path: str) -> str:
    base = str(request.base_url).rstrip("/")
    rel = "/" + path.lstrip("/")
    return f"{base}{rel}"

# --------------------------------- Schemas -----------------------------------

class SignupPayload(BaseModel):
    name: str
    email: EmailStr
    password: str

class LoginPayload(BaseModel):
    email: str
    password: str

class AccountVerificationPayload(BaseModel):
    email: EmailStr
    code: int

class PasswordResetCode(BaseModel):
    email: EmailStr

class VerifyCodePayload(BaseModel):
    email: EmailStr
    code: str

class ResetCodePayload(BaseModel):
    email: EmailStr
    code: str
    password: str

class UpdateProfilePayload(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    password: Optional[str] = None



# --------------------------------- Routes ------------------------------------

# ////////////////////////////  Sign up  ///////////////////////////////////////
@auth_router.post("/signup")
async def signup(payload: SignupPayload):
    user = await User.filter(email=payload.email).first()
    if user:
        raise HTTPException(status_code=400, detail="User already exists")
    try:
        user = User(
            name=payload.name,
            email=payload.email,
            password=ph.hash(payload.password),
        )
        await user.save()
        is_email_sent: bool = await generate_code("account_activation", user=user)
        if is_email_sent:
            return {"success": True, "verify": False, "detail": "Verification Email sent successfully"}
        else:
            await user.delete()
            raise HTTPException(status_code=500, detail="Failed to send verification email")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"server error {e}")

# ////////////////////////////  Sign in  ///////////////////////////////////////
@auth_router.post("/signin")
async def signin(data: LoginPayload):
    user = await User.filter(email=data.email).first()
    if not user:
        raise HTTPException(status_code=400, detail="User Not found")
    try:
        ph.verify(user.password, data.password)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Credentials.")

    if user.email_verified is False:
        is_email_sent: bool = await generate_code("account_activation", user=user)
        if is_email_sent:
            return {"success": True, "verify": False, "detail": "Email not verified, code sent"}
        else:
            raise HTTPException(status_code=400, detail="Email not verified, code not sent")

    try:
        token = generate_user_token({"id": user.id})
        return {
            "success": True,
            "token": token,
            "user": {
                "name": user.name,
                "email": user.email,
                "user_id": user.id,
                "role": user.role,
                # >>> include consent block
                "consent": {
                    "has_consent": bool(getattr(user, "consent_to_call", False)),
                    "note": getattr(user, "consent_note", None),
                    "updated_at": getattr(user, "consent_updated_at", None),
                },
            },
            "detail": "Login Successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ////////////////////////////  Delete Acccount  ///////////////////////////////
@auth_router.delete("/delete-account")
async def delete_account(user: Annotated[User, Depends(get_current_user)]):
    try:
        await user.delete()
        return {"success": True, "detail": "Account deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ////////////////////////////  Account Verification  //////////////////////////
@auth_router.post("/account-verification")
async def account_verification(payload: AccountVerificationPayload):
    user = await User.filter(email=payload.email).first()
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    code = await Code.filter(user__id=user.id).order_by("-id").first()
    if not code:
        raise HTTPException(detail="Invalid code", status_code=400)
    try:
        if code.value == str(payload.code):
            user.email_verified = True
            await user.save()
            confirmation_email(to_email=user.email)
            await code.delete()
            token = generate_user_token({"id": user.id})
            return {
                "success": True,
                "token": token,
                "user": {"name": user.name, "email": user.email},
                "detail": "Account verified successfully",
            }
        else:
            raise HTTPException(detail="Invalid code", status_code=400)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(detail="Invalid code", status_code=400)

# ////////////////////////////  Resend OTP  ////////////////////////////////////
@auth_router.post("/resend-otp")
async def resend_otp(payload: PasswordResetCode):
    user = await User.filter(email=payload.email).first()
    if not user:
        raise HTTPException(detail="Account not found", status_code=400)
    try:
        await generate_code("account_activation", user)
        return {"success": True, "detail": "Account activation code sent successfully"}
    except Exception as e:
        raise HTTPException(detail=str(e), status_code=500)

# ////////////////////////////  Password Reset Code  ///////////////////////////
@auth_router.post("/password-reset-code")
async def password_reset_code(payload: PasswordResetCode):
    user = await User.filter(email=payload.email).first()
    if not user:
        raise HTTPException(detail="Account not found", status_code=400)
    try:
        await generate_code("password_reset", user)
        return {"success": True, "detail": "Password reset code sent successfully"}
    except Exception as e:
        raise HTTPException(detail=str(e), status_code=500)

# ////////////////////////////  Confirm OTP  ///////////////////////////////////
@auth_router.post("/confirm-otp")
async def confirm_otp(payload: VerifyCodePayload):
    user = await User.filter(email=payload.email).first()
    if not user:
        raise HTTPException(detail="User not found", status_code=400)
    code = await Code.filter(user__id=user.id, type="password_reset").order_by("-id").first()
    if not code:
        raise HTTPException(detail="Invalid code", status_code=400)
    if payload.code == code.value:
        return {"success": True, "detail": "Otp verified successfully"}
    else:
        raise HTTPException(detail="Invalid code", status_code=400)

# ////////////////////////////  Validate Token  ////////////////////////////////
@auth_router.get("/validate-token")
async def validate_token(user: Annotated[User, Depends(get_current_user)]):
    if not user:
        raise HTTPException(detail="Un Authenticated", status_code=401)
    return {"success": True, "detail": "Token verified successfully"}

# ////////////////////////////  Reset Password  ////////////////////////////////
@auth_router.post("/reset-password")
async def reset_password(payload: ResetCodePayload):
    try:
        user = await User.filter(email=payload.email).first()
        if not user:
            raise HTTPException(detail="User not found", status_code=400)
        code = await Code.filter(user__id=user.id, type="password_reset").order_by("-id").first()
        if not code or payload.code != code.value:
            raise HTTPException(detail="Invalid code", status_code=400)
        user.password = ph.hash(payload.password)
        await user.save()
        await code.delete()
        return {"success": True, "detail": "Password reset successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(detail=str(e), status_code=400)

# ////////////////////////////  Update Profile  ////////////////////////////////
@auth_router.post("/update-profile")
async def update_profile(data: UpdateProfilePayload, user: Annotated[User, Depends(get_current_user)]):
    if data.email:
        existing = await User.filter(email=data.email).first()
        if existing and data.email != user.email:
            raise HTTPException(detail="Email already exists", status_code=400)
    if data.password:
        try:
            ph.verify(user.password, data.password)
        except Exception:
            raise HTTPException(status_code=403, detail="Current password is incorrect")
    try:
        if data.password:
            user.password = ph.hash(data.password)
        if data.name:
            user.name = data.name
        if data.email:
            user.email = data.email
        await user.save()
        return {
            "success": True,
            "data": {"name": user.name, "email": user.email},
            "detail": "Profile updated successfully",
        }
    except Exception as e:
        raise HTTPException(detail=str(e), status_code=400)

# ////////////////////////////  Profile Photo APIs  ////////////////////////////

@auth_router.post("/profile-photo")
async def upload_profile_photo(
    request: Request,
    file: UploadFile = File(...),
    user: Annotated[User, Depends(get_current_user)] = None,
):
    if file.content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        allowed = ", ".join(sorted(ALLOWED_IMAGE_CONTENT_TYPES))
        raise HTTPException(status_code=400, detail=f"Unsupported type. Allowed: {allowed}")
    content = await file.read()
    if len(content) > MAX_PROFILE_PHOTO_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Image too large. Max {MAX_PROFILE_PHOTO_BYTES // (1024*1024)} MB",
        )
    ext = _ext_from_content_type(file.content_type)
    new_filename = f"{uuid.uuid4().hex}{ext}"
    new_path = Path(PROFILE_PHOTO_STORAGE) / new_filename
    with open(new_path, "wb") as f:
        f.write(content)
    # delete old
    if user.profile_photo:
        try:
            old_file = Path(".") / user.profile_photo.lstrip("/")
            if not old_file.exists():
                old_file = Path(PROFILE_PHOTO_STORAGE) / Path(user.profile_photo).name
            if old_file.exists():
                old_file.unlink()
        except Exception:
            pass
    rel_url = f"{PROFILE_PHOTO_URL_PATH}/{new_filename}".replace("//", "/")
    user.profile_photo = rel_url
    await user.save()
    return {"success": True, "detail": "Uploaded successfully", "photo_url": _abs_url(request, rel_url)}

@auth_router.get("/profile-photo")
async def get_profile_photo(
    request: Request,
    redirect: Optional[bool] = False,
    user: Annotated[User, Depends(get_current_user)] = None,
):
    if not user.profile_photo:
        raise HTTPException(status_code=404, detail="No profile photo set")
    abs_url = _abs_url(request, user.profile_photo)
    if redirect:
        return RedirectResponse(url=abs_url)
    return {"success": True, "photo_url": abs_url}

@auth_router.delete("/profile-photo")
async def delete_profile_photo(user: Annotated[User, Depends(get_current_user)]):
    if not user.profile_photo:
        raise HTTPException(status_code=404, detail="No profile photo to delete")
    try:
        stored = str(user.profile_photo).lstrip("/")
        abs_path = Path(".") / stored
        if not abs_path.exists():
            abs_path = Path(PROFILE_PHOTO_STORAGE) / Path(stored).name
        if abs_path.exists():
            abs_path.unlink()
    except Exception:
        pass
    user.profile_photo = None
    await user.save()
    return {"success": True, "detail": "Profile photo deleted successfully"}

# ////////////////////////////  Get User info  //////////////////////////////////
@auth_router.get("/user-info")
async def get_user_info(request: Request, user: Annotated[User, Depends(get_current_user)]):
    rel = user.profile_photo
    abs_url = _abs_url(request, rel) if rel else None
    return {
        "success": True,
        "data": {
            "name": user.name,
            "email": user.email,
            "role": getattr(user, "role", None),
            "profile_photo": rel,
            "profile_photo_url": abs_url,
            # >>> include consent block
            "consent": {
                "has_consent": bool(getattr(user, "consent_to_call", False)),
                "note": getattr(user, "consent_note", None),
                "updated_at": getattr(user, "consent_updated_at", None),
            },
        },
    }

# ////////////////////////////  Change Password  ///////////////////////////////
class ChangePasswordPayload(BaseModel):
    old_password: str
    new_password: str

@auth_router.post("/change-password")
async def change_password(payload: ChangePasswordPayload, user: Annotated[User, Depends(get_current_user)]):
    try:
        try:
            ph.verify(user.password, payload.old_password)
        except Exception:
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        user.password = ph.hash(payload.new_password)
        await user.save()
        return {"success": True, "detail": "Password changed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error changing password: {str(e)}")

# ////////////////////////////  Consent APIs (NEW)  ////////////////////////////

# --------------------------- Consent: Schemas & Routes ---------------------------
from typing import Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field, constr
from fastapi import HTTPException, Depends
import logging

logger = logging.getLogger(__name__)

# Optional: set to True if your product should reject "False" confirmations server-side
REQUIRE_CONSENT_TRUE = False  # keep False if you only enforce this in the frontend

class ConsentPayload(BaseModel):
    """
    Client posts the user's explicit choice. 'note' is optional free text.
    """
    has_consent: bool = Field(..., description="Does the user have consent to call these leads?")
    note: Optional[constr(strip_whitespace=True, max_length=2000)] = Field(
        default=None, description="Optional description (how consent was obtained, source, tags, etc.)"
    )

class ConsentOut(BaseModel):
    """
    Server response with current state and whether client should still block access.
    needs_action=True means the user hasn't explicitly responded 'yes' yet.
    """
    has_consent: bool
    note: Optional[str] = None
    updated_at: Optional[datetime] = None
    needs_action: bool = Field(
        ..., description="True if user must still confirm consent before proceeding"
    )

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

@auth_router.get("/consent", response_model=ConsentOut)
async def get_consent(user: Annotated[User, Depends(get_current_user)]):
    """
    Return the user's current consent state.
    - needs_action is True until the user has *explicitly* confirmed consent (has_consent=True AND updated_at set).
    - If they explicitly *declined* (has_consent=False with updated_at set), needs_action stays True
      so your frontend can keep blocking until they decide to enable consent.
    """
    has = bool(getattr(user, "consent_to_call", False))
    ts  = getattr(user, "consent_updated_at", None)

    # needs_action = user must still *affirm* consent; a previous False still blocks
    needs_action = not (has and ts is not None)

    return ConsentOut(
        has_consent=has,
        note=getattr(user, "consent_note", None),
        updated_at=ts,
        needs_action=needs_action,
    )

@auth_router.post("/consent", response_model=ConsentOut)
async def set_consent(payload: ConsentPayload, user: Annotated[User, Depends(get_current_user)]):
    """
    Set/update the user's consent flag and optional note.
    - Idempotent: if nothing changed, returns current state.
    - Stores timestamp in UTC.
    - If REQUIRE_CONSENT_TRUE is True, rejects has_consent=False with 422.
    """
    try:
        new_has = bool(payload.has_consent)
        new_note = payload.note or None

        if REQUIRE_CONSENT_TRUE and not new_has:
            raise HTTPException(
                status_code=422,
                detail="Consent must be granted to continue. Please confirm you have consent to call these leads."
            )

        # Check idempotency
        if (
            new_has == bool(getattr(user, "consent_to_call", False)) and
            (new_note or "") == (getattr(user, "consent_note", None) or "")
        ):
            # No change → keep previous timestamp
            ts = getattr(user, "consent_updated_at", None)
            needs_action = not (new_has and ts is not None)
            return ConsentOut(
                has_consent=new_has,
                note=new_note,
                updated_at=ts,
                needs_action=needs_action,
            )

        # Apply changes
        user.consent_to_call = new_has
        user.consent_note = new_note
        user.consent_updated_at = _now_utc()
        await user.save(update_fields=["consent_to_call", "consent_note", "consent_updated_at"])

        logger.info(
            "Consent updated | user_id=%s has_consent=%s",
            getattr(user, "id", None),
            user.consent_to_call,
        )

        needs_action = not (user.consent_to_call and user.consent_updated_at is not None)

        return ConsentOut(
            has_consent=user.consent_to_call,
            note=user.consent_note,
            updated_at=user.consent_updated_at,
            needs_action=needs_action,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to update consent")
        raise HTTPException(status_code=500, detail=f"Failed to update consent: {str(e)}")

@auth_router.delete("/consent", response_model=ConsentOut)
async def reset_consent(user: Annotated[User, Depends(get_current_user)]):
    """
    Optional: Reset consent to default (as if never set).
    Useful for support/admin flows or if the user wants to redo onboarding.
    """
    user.consent_to_call = False
    user.consent_note = None
    user.consent_updated_at = None
    await user.save(update_fields=["consent_to_call", "consent_note", "consent_updated_at"])

    return ConsentOut(
        has_consent=False,
        note=None,
        updated_at=None,
        needs_action=True,
    )
