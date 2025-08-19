from fastapi import FastAPI
from controllers import assistant_controller, call_controller, lead_controller, twilio_controller,statistics_controller,documents_controller,hubspot_controller,admin_controller
from helpers.tortoise_config import lifespan
from controllers.auth_controller import auth_router
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from pathlib import Path
from controllers.impersonate_controller import impersonate_router
from starlette.middleware.trustedhost import TrustedHostMiddleware

# Path("media/profile_photos").mkdir(parents=True, exist_ok=True)

MEDIA_ROOT = os.getenv("PROFILE_PHOTO_STORAGE", "media/profile_photos")
media_parent = Path(MEDIA_ROOT).parent
media_parent.mkdir(parents=True, exist_ok=True)




app = FastAPI(lifespan=lifespan)
# app.mount("/media", StaticFiles(directory="media"), name="media")

app.mount("/media", StaticFiles(directory=str(media_parent)), name="media")

app.add_middleware(
    TrustedHostMiddleware, allowed_hosts=["*"]
)
app.include_router(auth_router, prefix='/api', tags=['Authentication'])
app.include_router(twilio_controller.router, prefix='/api', tags=['Twilio Controller'])
app.include_router(assistant_controller.router, prefix='/api', tags=['Assistant Controller'])
app.include_router(call_controller.router, prefix='/api', tags=['Call Controller'])
app.include_router(lead_controller.router, prefix='/api', tags=['Leads Controller'])
app.include_router(statistics_controller.router, prefix='/api', tags=['Statistics Controller'])
app.include_router(documents_controller.router, prefix='/api', tags=['Documents Controller'])
app.include_router(hubspot_controller.router, prefix='/api', tags=['HubSpot Controller'])
app.include_router(admin_controller.admin_router, prefix='/api/admin', tags=['Admin Controller'])
app.include_router(impersonate_router , prefix='/api' , tags=['Admin-Login-AsUser'])

app.add_middleware(
    CORSMiddleware, 
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    
)

@app.get('/')
def greetings():
    return {
        "Message": "Hello Developers, how are you :)"
    }