# from fastapi import FastAPI
# from controllers import assistant_controller, call_controller, lead_controller, twilio_controller,statistics_controller,documents_controller,hubspot_controller,admin_controller
# from helpers.tortoise_config import lifespan
# from controllers.auth_controller import auth_router
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.staticfiles import StaticFiles
# import os
# from pathlib import Path
# from controllers.impersonate_controller import impersonate_router
# from starlette.middleware.trustedhost import TrustedHostMiddleware
# from controllers.campaign_controller import router as campaign_router

# # Path("media/profile_photos").mkdir(parents=True, exist_ok=True)

# MEDIA_ROOT = os.getenv("PROFILE_PHOTO_STORAGE", "media/profile_photos")
# media_parent = Path(MEDIA_ROOT).parent
# media_parent.mkdir(parents=True, exist_ok=True)




# app = FastAPI(lifespan=lifespan)
# # app.mount("/media", StaticFiles(directory="media"), name="media")

# app.mount("/media", StaticFiles(directory=str(media_parent)), name="media")

# app.add_middleware(
#     TrustedHostMiddleware, allowed_hosts=["*"]
# )
# app.include_router(auth_router, prefix='/api', tags=['Authentication'])
# app.include_router(twilio_controller.router, prefix='/api', tags=['Twilio Controller'])
# app.include_router(assistant_controller.router, prefix='/api', tags=['Assistant Controller'])
# app.include_router(call_controller.router, prefix='/api', tags=['Call Controller'])
# app.include_router(lead_controller.router, prefix='/api', tags=['Leads Controller'])
# app.include_router(statistics_controller.router, prefix='/api', tags=['Statistics Controller'])
# app.include_router(documents_controller.router, prefix='/api', tags=['Documents Controller'])
# app.include_router(hubspot_controller.router, prefix='/api', tags=['HubSpot Controller'])
# app.include_router(admin_controller.admin_router, prefix='/api/admin', tags=['Admin Controller'])
# app.include_router(impersonate_router , prefix='/api' , tags=['Admin-Login-AsUser'])
# app.include_router(campaign_router, prefix="/api/campaigns", tags=["campaigns"])
# app.add_middleware(
#     CORSMiddleware, 
#     allow_origins=["http://localhost:5173"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
    
# )

# @app.get('/')
# def greetings():
#     return {
#         "Message": "Hello Developers, how are you :)"
#     }





from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI
from controllers import (
    assistant_controller,
    call_controller,
    lead_controller,
    twilio_controller,
    statistics_controller,
    documents_controller,
    crm_controller,
    admin_controller,
    appointment_controller,
    form_controller,
    
)
from helpers.tortoise_config import lifespan
from controllers.auth_controller import auth_router
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from pathlib import Path
from controllers.impersonate_controller import impersonate_router
from starlette.middleware.trustedhost import TrustedHostMiddleware
# Import the campaigns API router AND the scheduler hook to rehydrate jobs
from controllers.campaign_controller import (
    router as campaign_router,
    _schedule_campaign_job,  # used at startup to re-schedule active campaigns
)
from scheduler.campaign_scheduler import get_scheduler, reschedule_campaigns_on_startup, shutdown_scheduler
from controllers.form_controller import router as form_router
from helpers.intake_worker import start_scheduler, stop_scheduler
from controllers.intake_admin import router as intake_admin_router
# ----- Media setup -----
MEDIA_ROOT = os.getenv("PROFILE_PHOTO_STORAGE", "media/profile_photos")
media_parent = Path(MEDIA_ROOT).parent
media_parent.mkdir(parents=True, exist_ok=True)

app = FastAPI(lifespan=lifespan)

# Serve media (entire /media dir so nested folders work)
app.mount("/media", StaticFiles(directory=str(media_parent)), name="media")

# ----- Middlewares -----
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----- Routers -----
app.include_router(auth_router, prefix="/api", tags=["Authentication"])
app.include_router(twilio_controller.router, prefix="/api", tags=["Twilio Controller"])
app.include_router(assistant_controller.router, prefix="/api", tags=["Assistant Controller"])
app.include_router(call_controller.router, prefix="/api", tags=["Call Controller"])
app.include_router(appointment_controller.router , prefix="/api" , tags=["Appointments Controller"] )
app.include_router(lead_controller.router, prefix="/api", tags=["Leads Controller"])
app.include_router(statistics_controller.router, prefix="/api", tags=["Statistics Controller"])
app.include_router(documents_controller.router, prefix="/api", tags=["Documents Controller"])
app.include_router(crm_controller.router, prefix="/api", tags=["CRM Controller"])
app.include_router(admin_controller.admin_router, prefix="/api/admin", tags=["Admin Controller"])
app.include_router(impersonate_router, prefix="/api", tags=["Admin-Login-AsUser"])
app.include_router(campaign_router, prefix="/api/campaigns", tags=["campaigns"])
app.include_router(form_router,prefix="/api", tags=["Form details"] )
app.include_router(intake_admin_router, prefix="/api", tags=["intake-admin"])
# ----- Root -----
@app.get("/")
def greetings():
    return {"Message": "Hello Developers, how are you :)"}


# ======= Startup: Rehydrate campaign scheduler jobs =======
# Ensures that after a server restart, all active (scheduled/running) campaigns
# get their APScheduler cron job re-installed.
@app.on_event("startup")
async def _rehydrate_campaign_jobs():
    try:
        # Import inside the function to avoid circular import issues at import-time
        from models.campaign import Campaign, CampaignStatus

        active = await Campaign.filter(
            status__in=[CampaignStatus.SCHEDULED, CampaignStatus.RUNNING]
        ).all()

        for c in active:
            try:
                _schedule_campaign_job(c.id, c.timezone)
                print(f"[campaign scheduler] Rehydrated campaign {c.id} ({c.name})")
            except Exception as e:
                # Avoid crashing app startup because of a single campaign
                print(f"[campaign scheduler] Failed to rehydrate campaign {c.id}: {e}")

    except Exception as e:
        # If something fundamental fails, still let app boot; you can inspect logs.
        print(f"[campaign scheduler] Startup rehydration error: {e}")


app.add_event_handler("startup", start_scheduler(app))
app.add_event_handler("shutdown", stop_scheduler(app))


@app.on_event("startup")
async def _startup():
    # ensure scheduler exists
    get_scheduler()
    # reattach cron jobs for RUNNING/SCHEDULED campaigns
    await reschedule_campaigns_on_startup()

@app.on_event("shutdown")
async def _shutdown():
    shutdown_scheduler(wait=False)  