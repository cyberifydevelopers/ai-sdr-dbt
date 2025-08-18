import jwt
import os
from datetime import datetime
from jwt import InvalidTokenError
from models.auth import User
from fastapi import HTTPException
# def generate_user_token(payload: dict):
#     jwt_key = os.getenv("JWT_SECRET")
#     token = jwt.encode(payload, jwt_key, algorithm='HS256')
#     return token

# def decode_user_token(token: str):
#     jwt_key = os.getenv("JWT_SECRET")
#     return jwt.decode(token, jwt_key, algorithms=['HS256'])



def generate_user_token(user):
    jwt_key = os.getenv("JWT_SECRET")
    payload = {
        "user_id": user.id,
        "last_password_change": user.last_password_change.isoformat() if user.last_password_change else None,
        "iat": datetime.utcnow().timestamp()
    }
    token = jwt.encode(payload, jwt_key, algorithm='HS256')
    return token

async def decode_user_token(token: str):
    jwt_key = os.getenv("JWT_SECRET")
    try:
        payload = jwt.decode(token, jwt_key, algorithms=['HS256'])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await User.get_or_none(id=payload['user_id'])

    if not user:
        raise HTTPException(status_code=401, detail="User does not exist")

    token_password_change = payload.get('last_password_change')
    user_password_change = user.last_password_change.isoformat() if user.last_password_change else None

    if user_password_change and token_password_change != user_password_change:
        raise HTTPException(status_code=401, detail="Token invalidated due to password change")
    return {"id":user.id}
 