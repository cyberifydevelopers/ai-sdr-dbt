from typing import Literal, Union, Tuple, Annotated
from models.auth import User, Code
from fastapi import HTTPException
from datetime import datetime, timedelta
from helpers.email_generator import send_email, send_confirmation_email, send_reset_email, confirmation_email
import random




def send_reset_email(to_email: str, code: Union[str, int]) -> bool:
    """
    Send a password reset email to the user.

    Args:
        to_email (str): The recipient email.
        code (Union[str, int]): The reset code.

    Returns:
        bool: True if the email was sent successfully, False otherwise.
    """
    message_html = f"""
    <html>
      <head></head>
      <body>
        <p>Hi,<br>
           Here is your password reset code: <b>{code}</b><br>
           Please use this code to reset your password.
        </p>
      </body>
    </html>
    """
    return send_email(to_email, "Confirm Email to Reset Password", message_html)




async def generate_code(type: Literal["password_reset", "account_activation"], user: User) -> Tuple[Code, bool]:
    """
    Generates a code for account actions and sends the corresponding email.

    Args:
        type (Literal["password_reset", "account_activation"]): The type of code to generate.
        user (User): The user for whom the code is generated.
        db (Session): The database session.

    Returns:
        Tuple[Code, bool]: The created Code instance and a boolean indicating if the email was sent successfully.
    """
    try:
        code_value = str(random.randint(1000, 9999))
        code = Code(
            type=type,
            value=code_value,
            expires_at=datetime.utcnow() + timedelta(minutes=40),
            user=user
        )
        print(f"User Email: {user.email}")
        print(f"Verification Code: {code_value}")
        await code.save()
        if type == "password_reset":
            email_sent = send_reset_email(user.email, code_value)
        elif type == "account_activation":
            email_sent = send_confirmation_email(user.email, code_value)
        else:
            raise ValueError("Invalid code type provided.")

        return email_sent
    except Exception as e:
        # db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to generate code: {e}")

