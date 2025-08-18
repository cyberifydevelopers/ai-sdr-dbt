import jwt
import os
from fastapi.security import  HTTPBearer,HTTPAuthorizationCredentials
from fastapi import Depends, HTTPException
from typing import Annotated
from models.auth import User
security = HTTPBearer()


def generate_user_token(payload: dict):
    jwt_key = os.getenv("JWT_SECRET")
    token = jwt.encode(payload, jwt_key, algorithm='HS256')
    return token

def decode_user_token(token: str):
    jwt_key = os.getenv("JWT_SECRET")
    return jwt.decode(token, jwt_key, algorithms=['HS256'])

async def  get_current_user(token: Annotated[HTTPAuthorizationCredentials, Depends(security)]):
    print(token)
    token = token.credentials
    user_credential = decode_user_token(token = token)
    if user_credential:
        user = await User.filter(id=user_credential["id"]).first()
        if user:
            return user
        else:
            raise HTTPException(status_code=401, detail="Invalid Credentials")
    
async def admin_required(user: Annotated[User, Depends(get_current_user)]):
    """
    Dependency function to check if the current user has admin role
    """
    if not user.role or user.role.lower() != "admin":
        raise HTTPException(
            status_code=403, 
            detail="Admin access required"
        )
    return user
    
        
    