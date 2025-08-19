# import smtplib
# from email.mime.multipart import MIMEMultipart
# from email.mime.text import MIMEText
# import os
# import dotenv
# from typing import Union
# import datetime
# dotenv.load_dotenv()


# def send_email(to_address: str, subject: str, message_html: str):
#     user = os.getenv("SMTP_FROM_USER")
#     smtp_server = os.getenv("SMTP_SERVER")
#     smtp_port = int(os.getenv("SMTP_PORT"))
#     from_address = os.getenv("SMTP_FROM_ADDRESS")
#     password =  os.getenv('SMTP_PASSWORD')   
#     message = MIMEMultipart()
#     message["From"] = f"\"{user}\" <{from_address}>"
#     message["To"] = to_address
#     message["Subject"] = subject
#     html = message_html
#     message.attach(MIMEText(html, "html"))

#     try:
#         print(f"smtp_port: {smtp_port}")
#         print(f"smtp_server : {smtp_server}")
#         print(f"from_address: {from_address}")
#         print("user: ", user)
#         with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
#             server.login(from_address, password)
#             server.send_message(message)
#             return True
#     except Exception as e:
#         print(f"Failed to send email: {e}")
#         return False
    
# def send_confirmation_email(to_email: str, code: Union[str, int]):
#     message_html = f"""\
#     <!DOCTYPE html>
#     <html lang="en">
#     <head>
#         <meta charset="UTF-8">
#         <meta name="viewport" content="width=device-width, initial-scale=1.0">
#         <title>Email Activation</title>
#         <style>
#             /* General Styles */
#             body {{
#                 margin: 0;
#                 padding: 0;
#                 background-color: #f4f4f4;
#                 font-family: Arial, sans-serif;
#             }}
#             .email-container {{
#                 max-width: 600px;
#                 margin: 0 auto;
#                 background-color: #ffffff;
#                 border-radius: 8px;
#                 overflow: hidden;
#                 box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
#             }}
#             .header {{
#                 background-color: #2752D8;
#                 padding: 20px;
#                 text-align: center;
#             }}
#             .header img {{
#                 max-width: 150px;
#             }}
#             .body {{
#                 padding: 30px;
#                 color: #333333;
#             }}
#             .body h1 {{
#                 color: #2752D8;
#                 margin-bottom: 20px;
#                 font-size: 24px;
#             }}
#             .body p {{
#                 line-height: 1.6;
#                 font-size: 16px;
#             }}
#             .code-box {{
#                 background-color: #f0f4ff;
#                 border-left: 4px solid #2752D8;
#                 padding: 15px;
#                 margin: 20px 0;
#                 font-size: 18px;
#                 font-weight: bold;
#                 text-align: center;
#                 letter-spacing: 2px;
#                 color: #152B72;
#                 border-radius: 4px;
#             }}
#             .button {{
#                 display: inline-block;
#                 padding: 12px 25px;
#                 background-color: #2752D8;
#                 color: #ffffff;
#                 text-decoration: none;
#                 border-radius: 5px;
#                 font-weight: bold;
#                 transition: background-color 0.3s ease;
#             }}
#             .button:hover {{
#                 background-color: #1f3a99;
#             }}
#             .footer {{
#                 background-color: #f4f4f4;
#                 padding: 20px;
#                 text-align: center;
#                 font-size: 14px;
#                 color: #777777;
#             }}
#             .footer a {{
#                 color: #2752D8;
#                 text-decoration: none;
#             }}
#             @media only screen and (max-width: 600px) {{
#                 .body, .header, .footer {{
#                     padding: 15px;
#                 }}
#                 .button {{
#                     width: 100%;
#                     text-align: center;
#                 }}
#             }}
#         </style>
#     </head>
#     <body>
#         <div class="email-container">
#             <!-- Header Section -->
             
    
#             <!-- Body Section -->
#             <div class="body">
#                 <h1>Hello,</h1>
#                 <p>Please Enter the following verification code to log into OCR Rag AI</p>
#                 <div class="code-box">
#                     {code}
#                 </div>                
#                 <p>If you are having any issues with your account, please contact us at
#                 <span>
#                 support@ocrrag.ai
#                 </span>
                
#                 </p>
#             </div>
    
#             <!-- Footer Section -->
#             <div class="footer">
#                 <p>&copy; OCR Rag AI. All rights reserved.</p>
               
#             </div>
#         </div>
#     </body>
#     </html>
#     """
#     subject = "Confirm Email to Activate Account"
#     return send_email(to_email, subject, message_html)
    
# from typing import Union
# from datetime import datetime

# def confirmation_email(to_email: str):
#     message_html = f"""\
#     <!DOCTYPE html>
#     <html lang="en">
#     <head>
#         <meta charset="UTF-8">
#         <meta name="viewport" content="width=device-width, initial-scale=1.0">
#         <title>Email Activation</title>
#         <style>
#             /* General Styles */
#             body {{
#                 margin: 0;
#                 padding: 0;
#                 background-color: #f4f4f4;
#                 font-family: Arial, sans-serif;
#             }}
#             .email-container {{
#                 max-width: 600px;
#                 margin: 0 auto;
#                 background-color: #ffffff;
#                 border-radius: 8px;
#                 overflow: hidden;
#                 box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
#             }}
#             .header {{
#                 padding: 20px;
#                 text-align: center;
#             }}
#             .header img {{
#                 max-width: 150px;
#             }}
#             .body {{
#                 padding: 30px;
#                 color: #333333;
#             }}
#             .body h1 {{
#                 color: #2752D8;
#                 margin-bottom: 20px;
#                 font-size: 24px;
#             }}
#             .body p {{
#                 line-height: 1.6;
#                 font-size: 16px;
#             }}
#             .code-box {{
#                 background-color: #f0f4ff;
#                 border-left: 4px solid #2752D8;
#                 padding: 15px;
#                 margin: 20px 0;
#                 font-size: 18px;
#                 font-weight: bold;
#                 text-align: center;
#                 letter-spacing: 2px;
#                 color: #152B72;
#                 border-radius: 4px;
#             }}
#             .button {{
#                 display: inline-block;
#                 padding: 12px 25px;
#                 background-color: #2752D8;
#                 color: #ffffff;
#                 text-decoration: none;
#                 border-radius: 5px;
#                 font-weight: bold;
#                 transition: background-color 0.3s ease;
#                 margin-top: 20px;
#             }}
#             .button:hover {{
#                 background-color: #1f3a99;
#             }}
#             .footer {{
#                 background-color: #f4f4f4;
#                 padding: 20px;
#                 text-align: center;
#                 font-size: 14px;
#                 color: #777777;
#             }}
#             .footer a {{
#                 color: #2752D8;
#                 text-decoration: none;
#             }}
#             @media only screen and (max-width: 600px) {{
#                 .body, .header, .footer {{
#                     padding: 15px;
#                 }}
#                 .button {{
#                     width: 100%;
#                     text-align: center;
#                 }}
#             }}
#         </style>
#     </head>
#     <body>
#         <div class="email-container">
#             <!-- Header Section -->
#             <div class="header">
#             </div>
    
#             <!-- Body Section -->
#             <div class="body">
#                 <h1>Hello,</h1>
                
#                 <!-- Welcome Message -->
#                 <p>Welcome to OCR Rag AI!<br>
#                 We’re thrilled to have you with us! To begin, simply sign in and start planning. If you have any planning questions, just ask your AI expert. For anything else, please contact <a href="mailto:support@ocrrag.ai">support@ocrrag.ai</a>.</p>
                
                
#             </div>
    
#             <!-- Footer Section -->
#             <div class="footer">
#                 <p>&copy; {datetime.now().year} OCR Rag AI. All rights reserved.</p>
               
#             </div>
#         </div>
#     </body>
#     </html>
#     """
#     subject = "Account Activated"
#     return send_email(to_email, subject, message_html)


# def send_reset_email(to_email: str, code: Union[str, int]):
   
    
#     message_html = f"""\
#     <!DOCTYPE html>
#     <html lang="en">
#     <head>
#         <meta charset="UTF-8">
#         <meta name="viewport" content="width=device-width, initial-scale=1.0">
#         <title>Password Reset</title>
#         <style>
#             /* General Styles */
#             body {{
#                 margin: 0;
#                 padding: 0;
#                 background-color: #f4f4f4;
#                 font-family: Arial, sans-serif;
#             }}
#             .email-container {{
#                 max-width: 600px;
#                 margin: 0 auto;
#                 background-color: #ffffff;
#                 border-radius: 8px;
#                 overflow: hidden;
#                 box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
#             }}
#             .header {{
#                 background-color: #2752D8;
#                 padding: 20px;
#                 text-align: center;
#             }}
#             .header img {{
#                 max-width: 150px;
#             }}
#             .body {{
#                 padding: 30px;
#                 color: #333333;
#             }}
#             .body h1 {{
#                 color: #2752D8;
#                 margin-bottom: 20px;
#                 font-size: 24px;
#             }}
#             .body p {{
#                 line-height: 1.6;
#                 font-size: 16px;
#             }}
#             .code-box {{
#                 background-color: #f0f4ff;
#                 border-left: 4px solid #2752D8;
#                 padding: 15px;
#                 margin: 20px 0;
#                 font-size: 18px;
#                 font-weight: bold;
#                 text-align: center;
#                 letter-spacing: 2px;
#                 color: #152B72;
#                 border-radius: 4px;
#             }}
#             .button {{
#                 display: inline-block;
#                 padding: 12px 25px;
#                 background-color: #2752D8;
#                 color: #ffffff;
#                 text-decoration: none;
#                 border-radius: 5px;
#                 font-weight: bold;
#                 transition: background-color 0.3s ease;
#             }}
#             .button:hover {{
#                 background-color: #1f3a99;
#             }}
#             .footer {{
#                 background-color: #f4f4f4;
#                 padding: 20px;
#                 text-align: center;
#                 font-size: 14px;
#                 color: #777777;
#             }}
#             .footer a {{
#                 color: #2752D8;
#                 text-decoration: none;
#             }}
#             @media only screen and (max-width: 600px) {{
#                 .body, .header, .footer {{
#                     padding: 15px;
#                 }}
#                 .button {{
#                     width: 100%;
#                     text-align: center;
#                 }}
#             }}
#         </style>
#     </head>
#     <body>
#         <div class="email-container">
#             <!-- Header Section -->
#             <div class="header">
               
#             </div>
    
#             <!-- Body Section -->
#             <div class="body">
#                 <h1>Hello,</h1>
#                 <p>You have requested to reset your password for your <strong>OCR Rag AI</strong> account. Please use the reset code below to proceed:</p>
                
#                 <div class="code-box">
#                     {code}
#                 </div>
                
#                 <p>If you did not request this password reset, please ignore this email or contact our support team.</p>
#                 <p>For any assistance, feel free to reach out to us.</p>
#             </div>
    
#             <!-- Footer Section -->
#             <div class="footer">
#                 <p>&copy; OCR Rag AI. All rights reserved.</p>
                
#             </div>
#         </div>
#     </body>
#     </html>
#     """
#     subject = "Confirm Email to Reset Password"
#     return send_email(to_email, subject, message_html)















import os
import re
import smtplib
import dotenv
from typing import Union, Optional
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

dotenv.load_dotenv()

# =========================
# SMTP helper
# =========================
def send_email(
    to_address: str,
    subject: str,
    message_html: str,
    message_text: Optional[str] = None,
) -> bool:
    """
    Sends an email using environment variables:
      SMTP_SERVER, SMTP_PORT, SMTP_FROM_ADDRESS, SMTP_FROM_USER, SMTP_PASSWORD
      (optional) SMTP_USERNAME (overrides login user), SMTP_USE_TLS ("1" or "true")
    """

    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    from_address = os.getenv("SMTP_FROM_ADDRESS")
    display_name = os.getenv("SMTP_FROM_USER", "AI-SDR-DBT")
    username = os.getenv("SMTP_USERNAME") or from_address
    password = os.getenv("SMTP_PASSWORD")
    use_tls = (os.getenv("SMTP_USE_TLS", "").lower() in {"1", "true", "yes"}) or smtp_port == 587

    if not (smtp_server and smtp_port and from_address and password):
        print("SMTP config missing one of SMTP_SERVER/SMTP_PORT/SMTP_FROM_ADDRESS/SMTP_PASSWORD")
        return False

    # Build a MIME "alternative" (HTML + plaintext) message
    msg = MIMEMultipart("alternative")
    msg["From"] = f"\"{display_name}\" <{from_address}>"
    msg["To"] = to_address
    msg["Subject"] = subject

    if not message_text:
        # crude HTML strip for plaintext fallback
        text = re.sub(r"<br\s*/?>", "\n", message_html, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        message_text = text

    msg.attach(MIMEText(message_text, "plain", "utf-8"))
    msg.attach(MIMEText(message_html, "html", "utf-8"))

    try:
        print(f"smtp_server: {smtp_server}")
        print(f"smtp_port  : {smtp_port}")
        print(f"from       : {from_address}")
        print(f"login user : {username} (display: {display_name})")
        if use_tls:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(username, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
                server.login(username, password)
                server.send_message(msg)
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False


# =========================
# THEME (Neon Blue, animated)
# =========================
def _neon_frame(inner: str, *, title: str = "AI-SDR-DBT", footer_note: str = "") -> str:
    """
    Wraps provided HTML in a robust, email-friendly neon/animated shell.
    Animations will gracefully degrade in clients that don't support them.
    """
    year = datetime.now().year
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<!-- Some clients strip HEAD styles; we keep critical bits inline as well. -->
<style>
  /* ====== Variables ====== */
  :root {{
    --bg-0: #070a17;
    --bg-1: #0b122b;
    --panel: rgba(255,255,255,0.06);
    --panel-border: rgba(59,130,246,0.45);
    --neon: #3b82f6;    /* blue-600 */
    --neon-cyan: #22d3ee; /* cyan-400 */
    --text: #e5ecff;
    --muted: #9db3ff;
    --shadow: rgba(59,130,246,0.35);
  }}

  /* ====== Animations (supported by Apple Mail/iOS/Gmail app; degrade elsewhere) ====== */
  @keyframes bgShift {{
    0% {{ background-position: 0% 50%; }}
    50% {{ background-position: 100% 50%; }}
    100% {{ background-position: 0% 50%; }}
  }}
  @keyframes glowPulse {{
    0%, 100% {{ box-shadow: 0 0 0px var(--shadow), 0 0 0px var(--neon); }}
    50% {{ box-shadow: 0 0 24px var(--shadow), 0 0 6px var(--neon); }}
  }}
  @keyframes floaty {{
    0%, 100% {{ transform: translateY(0px); }}
    50% {{ transform: translateY(-3px); }}
  }}
  @keyframes shine {{
    0% {{ transform: translateX(-150%); }}
    100% {{ transform: translateX(150%); }}
  }}

  /* ====== Layout ====== */
  body {{
    margin:0; padding:0;
    background: linear-gradient(120deg, var(--bg-0), var(--bg-1), var(--bg-0));
    background-size: 200% 200%;
    animation: bgShift 14s ease-in-out infinite;
    font-family: Arial, Helvetica, sans-serif;
    color: var(--text);
  }}
  .wrap {{
    width: 100%;
    padding: 24px 12px;
  }}
  .card {{
    max-width: 680px;
    margin: 0 auto;
    background: var(--panel);
    border: 1px solid var(--panel-border);
    border-radius: 16px;
    overflow: hidden;
    animation: glowPulse 4s ease-in-out infinite;
  }}
  .header {{
    padding: 28px 24px;
    text-align: center;
    position: relative;
  }}
  .logo {{
    display:inline-block;
    font-weight: 800;
    font-size: 20px;
    letter-spacing: 0.6px;
    color: var(--text);
    text-shadow: 0 0 8px rgba(59,130,246,.6), 0 0 18px rgba(34,211,238,.35);
    border: 1px solid rgba(34,211,238,.4);
    border-radius: 999px;
    padding: 10px 16px;
    animation: floaty 6s ease-in-out infinite;
  }}
  .tagline {{
    color: var(--muted);
    font-size: 12px;
    margin-top: 8px;
  }}
  .body {{
    padding: 28px 24px 8px 24px;
    line-height: 1.6;
    font-size: 16px;
  }}
  .title {{
    font-size: 22px;
    margin: 0 0 10px 0;
    color: #ffffff;
    text-shadow: 0 0 10px rgba(59,130,246,.55);
  }}
  .pill {{
    display:inline-block;
    padding: 6px 10px;
    border-radius: 999px;
    border: 1px solid rgba(59,130,246,.35);
    background: linear-gradient(90deg, rgba(59,130,246,.15), rgba(34,211,238,.15));
    font-size: 12px;
    letter-spacing: 0.3px;
    margin-bottom: 10px;
  }}
  .codebox {{
    margin: 18px 0 12px 0;
    padding: 18px 16px;
    text-align: center;
    font-weight: 800;
    font-size: 26px;
    letter-spacing: 3px;
    border-radius: 12px;
    color: #e6f4ff;
    background: radial-gradient(110% 140% at 50% 0%, rgba(59,130,246,.18), rgba(34,211,238,.10) 70%, transparent 100%);
    border: 1px solid rgba(59,130,246,.45);
    text-shadow: 0 0 8px rgba(59,130,246,.6), 0 0 20px rgba(34,211,238,.4);
    animation: glowPulse 3.6s ease-in-out infinite;
  }}
  .cta {{
    display:inline-block;
    position: relative;
    padding: 12px 22px;
    background: linear-gradient(90deg, #2563eb, #22d3ee);
    color: #0b122b !important;
    text-decoration: none;
    font-weight: 800;
    border-radius: 12px;
    border: 1px solid rgba(34,211,238,.6);
    overflow: hidden;
  }}
  .cta span.shine {{
    position:absolute;
    top:0; left:-150%;
    width: 60%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,.5), transparent);
    animation: shine 2.6s ease-in-out infinite;
  }}
  .footer {{
    padding: 16px 24px 26px 24px;
    color: #b8c5ff;
    font-size: 12px;
    text-align:center;
  }}
  .hr {{
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(59,130,246,.35), transparent);
    margin: 16px 0;
  }}
</style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="header">
        <div class="logo">AI-SDR-DBT • Voice Bot</div>
        <div class="tagline">Conversational SDR automation • Neon-powered UI</div>
      </div>

      <div class="body">
        <div class="pill">{title}</div>
        {inner}
      </div>

      <div class="footer">
        <div class="hr"></div>
        {footer_note}
        <div style="margin-top:10px;">&copy; {year} AI-SDR-DBT. All rights reserved.</div>
      </div>
    </div>
  </div>
</body>
</html>
"""


# =========================
# TEMPLATES
# =========================
def _verification_inner(code: Union[str, int]) -> str:
    return f"""
      <h1 class="title">Verify your sign-in</h1>
      <p>Use the one-time code below to continue into <strong>AI-SDR-DBT</strong>.</p>
      <div class="codebox">{code}</div>
      <p style="margin-top:10px;color:#cfe1ff;">This code expires soon. If you didn’t request it, you can safely ignore this email.</p>
      <div style="margin-top:18px;">
        <a class="cta" href="#" onclick="return false;"><span class="shine"></span>Open AI-SDR-DBT</a>
      </div>
    """

def _welcome_inner() -> str:
    return """
      <h1 class="title">Welcome aboard! 🚀</h1>
      <p><strong>AI-SDR-DBT</strong> is your voice-bot SDR that books meetings, nurtures leads, and answers calls 24/7.</p>
      <p>Jump in, connect your numbers, and start talking to customers in minutes.</p>
      <div style="margin-top:18px;">
        <a class="cta" href="#" onclick="return false;"><span class="shine"></span>Go to Dashboard</a>
      </div>
    """

def _reset_inner(code: Union[str, int]) -> str:
    return f"""
      <h1 class="title">Password reset</h1>
      <p>Use the following code to reset your password for <strong>AI-SDR-DBT</strong>:</p>
      <div class="codebox">{code}</div>
      <p style="margin-top:10px;color:#cfe1ff;">Didn’t request this? You can ignore this message.</p>
      <div style="margin-top:18px;">
        <a class="cta" href="#" onclick="return false;"><span class="shine"></span>Return to Sign-in</a>
      </div>
    """


# =========================
# Public API
# =========================
def send_confirmation_email(to_email: str, code: Union[str, int]) -> bool:
    subject = "Your AI-SDR-DBT verification code"
    html = _neon_frame(
        _verification_inner(code),
        title="Secure Sign-in",
        footer_note='Need help? Email <a href="mailto:support@ai-sdr-dbt.com" style="color:#9ad8ff;text-decoration:none;">support@ai-sdr-dbt.com</a>',
    )
    return send_email(to_email, subject, html)

def confirmation_email(to_email: str) -> bool:
    subject = "Welcome to AI-SDR-DBT — Account Activated"
    html = _neon_frame(
        _welcome_inner(),
        title="Account Activated",
        footer_note='Questions? Reach out at <a href="mailto:support@ai-sdr-dbt.com" style="color:#9ad8ff;text-decoration:none;">support@ai-sdr-dbt.com</a>',
    )
    return send_email(to_email, subject, html)

def send_reset_email(to_email: str, code: Union[str, int]) -> bool:
    subject = "AI-SDR-DBT password reset code"
    html = _neon_frame(
        _reset_inner(code),
        title="Security • Reset",
        footer_note='If this wasn’t you, please contact <a href="mailto:support@ai-sdr-dbt.com" style="color:#9ad8ff;text-decoration:none;">support@ai-sdr-dbt.com</a>',
    )
    return send_email(to_email, subject, html)
