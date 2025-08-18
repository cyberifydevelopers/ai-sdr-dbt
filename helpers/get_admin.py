from fastapi import Depends, HTTPException, status
from tortoise.exceptions import DoesNotExist
from models.auth import User
from helpers.user_token import decode_user_token
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Annotated

security = HTTPBearer()

async def get_admin(credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]):
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
    
    try:
        user = await User.get(id=user_id)
        if not user.email_confirmed:
            raise credentials_exception
        if not user.role == "admin":
            raise credentials_exception
        return user
    except:
        raise credentials_exception
    


async def get_admin_and_manager(credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]):
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
    
    try:
        user = await User.get(id=user_id)
        if not user.email_confirmed:
            raise credentials_exception
        if not user.role in ["admin", "sales_manager"]:
            raise credentials_exception
        return user
    except:
        raise credentials_exception