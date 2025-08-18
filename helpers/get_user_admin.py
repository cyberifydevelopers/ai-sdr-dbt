from fastapi import Depends, HTTPException, status
from tortoise.exceptions import DoesNotExist
from models.auth import User
from helpers.user_token import decode_user_token
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Annotated

security = HTTPBearer()

async def get_user_admin(credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]):
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload =await decode_user_token(token)
        user_id = payload["id"]
    except:
        raise credentials_exception
    
    if user_id is None:
        raise credentials_exception
    user = await User.get(id=user_id)
    if not user.role == 'admin':
        try:
            main_admin = await User.filter(company_id=user.company_id, main_admin = True).first()
            if main_admin is None or not main_admin.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Main admin account is inactive. User has been logged out.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        except:
            raise credentials_exception
    try:
        if not user.email_confirmed:
            raise credentials_exception
        main_admin = await User.filter(company_id=user.company_id, main_admin=True, role="company_admin").first()

        return main_admin
    except:
        raise credentials_exception