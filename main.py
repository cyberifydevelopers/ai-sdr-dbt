# from dotenv import load_dotenv
# load_dotenv()

# from fastapi import FastAPI
# import asyncio
# import os
# from pathlib import Path

# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.staticfiles import StaticFiles
# from starlette.middleware.trustedhost import TrustedHostMiddleware

# from helpers.tortoise_config import lifespan

# # ----- Routers / controllers -----
# from controllers.auth_controller import auth_router
# from controllers import (
#     assistant_controller,
#     call_controller,
#     lead_controller,
#     twilio_controller,
#     statistics_controller,
#     documents_controller,
#     crm_controller,
#     admin_controller,
#     appointment_controller,
#     form_controller,
# )

# from controllers.impersonate_controller import impersonate_router

# # Campaigns (+ rehydration helpers)
# from controllers.campaign_controller import (
#     router as campaign_router,
#     _schedule_campaign_job,  # used at startup to re-schedule active campaigns
# )
# from scheduler.campaign_scheduler import (
#     get_scheduler,
#     reschedule_campaigns_on_startup,
#     shutdown_scheduler,
# )

# from controllers.form_controller import router as form_router
# from helpers.intake_worker import start_scheduler, stop_scheduler
# from controllers.intake_admin import router as intake_admin_router
# from controllers.facebook_leads_controller import router as facebook_router

# # >>> Text Assistant (ALWAYS-ON DAEMONS) <<<
# # Import the API router plus daemon lifecycle helpers.
# # The controller exposes:
# #   - text_assistant_router: all SMS + daemon endpoints
# #   - start_text_daemons(): spins up scheduled + unscheduled loops (idempotent)
# #   - stop_text_daemons(): cancels the loops on shutdown
# from controllers.text_assistant_controller import (
#     router as text_assistant_router,
#     start_text_daemons,
#     stop_text_daemons,
# )

# from controllers.vapi_server_url import router as vapi_server_url

# # ----- Media setup -----
# MEDIA_ROOT = os.getenv("PROFILE_PHOTO_STORAGE", "media/profile_photos")
# media_parent = Path(MEDIA_ROOT).parent
# media_parent.mkdir(parents=True, exist_ok=True)

# app = FastAPI(lifespan=lifespan)

# # Serve media (entire /media dir so nested folders work)
# app.mount("/media", StaticFiles(directory=str(media_parent)), name="media")

# # ----- Middlewares -----
# app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*", "http://localhost:5173"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # ----- Routers -----
# app.include_router(auth_router, prefix="/api", tags=["Authentication"])
# app.include_router(twilio_controller.router, prefix="/api", tags=["Twilio Controller"])
# app.include_router(assistant_controller.router, prefix="/api", tags=["Assistant Controller"])
# app.include_router(call_controller.router, prefix="/api", tags=["Call Controller"])
# app.include_router(appointment_controller.router, prefix="/api", tags=["Appointments Controller"])
# app.include_router(lead_controller.router, prefix="/api", tags=["Leads Controller"])
# app.include_router(statistics_controller.router, prefix="/api", tags=["Statistics Controller"])
# app.include_router(documents_controller.router, prefix="/api", tags=["Documents Controller"])
# app.include_router(crm_controller.router, prefix="/api", tags=["CRM Controller"])
# app.include_router(admin_controller.admin_router, prefix="/api/admin", tags=["Admin Controller"])
# app.include_router(impersonate_router, prefix="/api", tags=["Admin-Login-AsUser"])
# app.include_router(campaign_router, prefix="/api/campaigns", tags=["campaigns"])
# app.include_router(form_router, prefix="/api", tags=["Form details"])
# app.include_router(intake_admin_router, prefix="/api", tags=["intake-admin"])
# app.include_router(facebook_router, prefix="/api/facebook", tags=["Facebook Routes"])
# app.include_router(text_assistant_router, prefix="/api", tags=["Text Assistant Controller"])
# app.include_router(vapi_server_url, prefix="/api")

# # ----- Root -----
# @app.get("/")
# def greetings():
#     return {"Message": "Hello Developers, how are you :)"}

# # ======= Startup: Rehydrate campaign scheduler jobs =======
# # Ensures that after a server restart, all active (scheduled/running) campaigns
# # get their APScheduler cron job re-installed.
# @app.on_event("startup")
# async def _rehydrate_campaign_jobs():
#     try:
#         # Import inside the function to avoid circular import issues at import-time
#         from models.campaign import Campaign, CampaignStatus

#         active = await Campaign.filter(
#             status__in=[CampaignStatus.SCHEDULED, CampaignStatus.RUNNING]
#         ).all()

#         for c in active:
#             try:
#                 _schedule_campaign_job(c.id, c.timezone)
#                 print(f"[campaign scheduler] Rehydrated campaign {c.id} ({c.name})")
#             except Exception as e:
#                 # Avoid crashing app startup because of a single campaign
#                 print(f"[campaign scheduler] Failed to rehydrate campaign {c.id}: {e}")

#     except Exception as e:
#         # If something fundamental fails, still let app boot; you can inspect logs.
#         print(f"[campaign scheduler] Startup rehydration error: {e}")

# # Intake worker lifecycle (unchanged)
# app.add_event_handler("startup", start_scheduler(app))
# app.add_event_handler("shutdown", stop_scheduler(app))

# # ======= Startup: general scheduler + campaign reschedule =======
# @app.on_event("startup")
# async def _startup_general():
#     # Ensure APS scheduler exists for campaigns and other cron tasks
#     get_scheduler()
#     await reschedule_campaigns_on_startup()

# # ======= Texting Daemons: start on boot, stop on shutdown =======
# @app.on_event("startup")
# async def _start_text_daemons_on_boot():
#     """
#     Start the always-on texting daemons (scheduled + unscheduled).
#     They tick every `tick_interval_seconds` (default 120) and
#     automatically process newly-eligible appointments.
#     """
#     try:
#         # start_text_daemons() is idempotent; safe to call once per process
#         start_text_daemons()
#         print("[text daemons] started (scheduled + unscheduled)")
#     except Exception as e:
#         print("[text daemons] failed to start:", e)

# @app.on_event("shutdown")
# async def _stop_text_daemons_on_shutdown():
#     """
#     Cleanly cancel daemon tasks so we don't keep stray loops around.
#     """
#     try:
#         stop_text_daemons()
#         print("[text daemons] stopped")
#     except Exception as e:
#         print("[text daemons] failed to stop:", e)

# # ======= Shutdown: campaign scheduler =======
# @app.on_event("shutdown")
# async def _shutdown_schedulers():
#     # Stop APScheduler (campaigns, etc.)
#     shutdown_scheduler(wait=False)
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
import asyncio
import os
from pathlib import Path

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from helpers.tortoise_config import lifespan

# ----- Routers / controllers -----
from controllers.auth_controller import auth_router
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

from controllers.impersonate_controller import impersonate_router

# Campaigns (+ rehydration helpers)
from controllers.campaign_controller import (
    router as campaign_router,
    _schedule_campaign_job,  # used at startup to re-schedule active campaigns
)
from scheduler.campaign_scheduler import (
    get_scheduler,
    reschedule_campaigns_on_startup,
    shutdown_scheduler,
)

from controllers.form_controller import router as form_router
from helpers.intake_worker import start_scheduler, stop_scheduler
from controllers.intake_admin import router as intake_admin_router
from controllers.facebook_leads_controller import router as facebook_router
from controllers.stripe_controller import router as stripe_controller

# >>> Text Assistant API + scheduler nudge <<<
from controllers.text_assistant_controller import (
    router as text_assistant_router,
    schedule_texting_job,   # <-- this exists in your controller
)

from controllers.vapi_server_url import router as vapi_server_url

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
    allow_origins=["*", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----- Routers -----
app.include_router(auth_router, prefix="/api", tags=["Authentication"])
app.include_router(twilio_controller.router, prefix="/api", tags=["Twilio Controller"])
app.include_router(assistant_controller.router, prefix="/api", tags=["Assistant Controller"])
app.include_router(call_controller.router, prefix="/api", tags=["Call Controller"])
app.include_router(appointment_controller.router, prefix="/api", tags=["Appointments Controller"])
app.include_router(lead_controller.router, prefix="/api", tags=["Leads Controller"])
app.include_router(statistics_controller.router, prefix="/api", tags=["Statistics Controller"])
app.include_router(documents_controller.router, prefix="/api", tags=["Documents Controller"])
app.include_router(crm_controller.router, prefix="/api", tags=["CRM Controller"])
app.include_router(admin_controller.admin_router, prefix="/api/admin", tags=["Admin Controller"])
app.include_router(impersonate_router, prefix="/api", tags=["Admin-Login-AsUser"])
app.include_router(campaign_router, prefix="/api/campaigns", tags=["campaigns"])
app.include_router(form_router, prefix="/api", tags=["Form details"])
app.include_router(intake_admin_router, prefix="/api", tags=["intake-admin"])
app.include_router(facebook_router, prefix="/api/facebook", tags=["Facebook Routes"])
app.include_router(text_assistant_router, prefix="/api", tags=["Text Assistant Controller"])
app.include_router(vapi_server_url, prefix="/api")
app.include_router(stripe_controller , prefix="/api" , tags={"Stripe Controller"})

# ----- Root -----
@app.get("/")
def greetings():
    return {"Message": "Hello Developers, how are you :)"}

# ======= Startup: Rehydrate campaign scheduler jobs =======
@app.on_event("startup")
async def _rehydrate_campaign_jobs():
    try:
        from models.campaign import Campaign, CampaignStatus
        active = await Campaign.filter(
            status__in=[CampaignStatus.SCHEDULED, CampaignStatus.RUNNING]
        ).all()
        for c in active:
            try:
                _schedule_campaign_job(c.id, c.timezone)
                print(f"[campaign scheduler] Rehydrated campaign {c.id} ({c.name})")
            except Exception as e:
                print(f"[campaign scheduler] Failed to rehydrate campaign {c.id}: {e}")
    except Exception as e:
        print(f"[campaign scheduler] Startup rehydration error: {e}")

# Intake worker lifecycle (unchanged)
app.add_event_handler("startup", start_scheduler(app))
app.add_event_handler("shutdown", stop_scheduler(app))

# ======= Startup: general scheduler + campaign reschedule =======
@app.on_event("startup")
async def _startup_general():
    get_scheduler()
    await reschedule_campaigns_on_startup()
    # start the ALWAYS-ON texting daemon loops (scheduled + unscheduled)
    try:
        tz = os.getenv("APS_TIMEZONE", "UTC")
        schedule_texting_job(tz)   # nudges loops + periodic keepalive nudges
    except Exception as e:
        print("[text scheduler] failed to schedule texting job:", e)

# Optionally trigger an immediate tick once on boot (doesn't block startup)
@app.on_event("startup")
async def _kickoff_text_jobs():
    try:
        from controllers.text_assistant_controller import run_texting_job, run_unscheduled_texting_job
        asyncio.create_task(run_texting_job())
        asyncio.create_task(run_unscheduled_texting_job())
        print("[text scheduler] kickoff: triggered scheduled & unscheduled texting jobs")
    except Exception as e:
        print("[text scheduler] kickoff error:", e)

# ======= Shutdown: campaign scheduler =======
@app.on_event("shutdown")
async def _shutdown_schedulers():
    shutdown_scheduler(wait=False)
