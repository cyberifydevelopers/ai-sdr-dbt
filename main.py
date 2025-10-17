
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

# # from controllers.email_assistant import schedule_email_job
# # schedule_email_job(timezone="UTC")
# from controllers.form_controller import router as form_router
# from helpers.intake_worker import start_scheduler, stop_scheduler
# from controllers.intake_admin import router as intake_admin_router
# from controllers.facebook_leads_controller import router as facebook_router
# from controllers.stripe_controller import router as stripe_controller
# from controllers.calldetails_controller import router as call_details
# # >>> Text Assistant API + scheduler nudge <<<
# from controllers.text_assistant_controller import (
#     router as text_assistant_router,
#     # schedule_texting_job,   # <-- this exists in your controller
# )
# from controllers.admin_billing import router as admin_payment_controls
# from controllers.vapi_server_url import router as vapi_server_url
# from controllers.Calendar_controller import router as CalenderController
# from helpers.interest_scheduler import run_interest_scheduler
# # from controllers.email_assistant import router as emailassistant
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
# app.include_router(facebook_router, prefix="/api", tags=["Facebook Routes"])
# app.include_router(text_assistant_router, prefix="/api", tags=["Text Assistant Controller"])
# app.include_router(vapi_server_url, prefix="/api")
# app.include_router(stripe_controller , prefix="/api" , tags={"Stripe Controller"})
# app.include_router(CalenderController , prefix="/api"  , tags={"Calender Controller"})
# app.include_router(call_details , prefix="/api"   , tags={"User Call Logs"})
# # app.include_router (emailassistant , prefix="/api" , tags={"Email Assistant"} )
# app.include_router(admin_payment_controls , prefix="/api"   , tags={"admin payment controls"})
# # ----- Root -----
# @app.get("/")
# def greetings():
#     return {"Message": "Hello Developers, how are you :)"}

# # ======= Startup: Rehydrate campaign scheduler jobs =======
# @app.on_event("startup")
# async def _rehydrate_campaign_jobs():
#     try:
#         from models.campaign import Campaign, CampaignStatus
#         active = await Campaign.filter(
#             status__in=[CampaignStatus.SCHEDULED, CampaignStatus.RUNNING]
#         ).all()
#         for c in active:
#             try:
#                 _schedule_campaign_job(c.id, c.timezone)
#                 print(f"[campaign scheduler] Rehydrated campaign {c.id} ({c.name})")
#             except Exception as e:
#                 print(f"[campaign scheduler] Failed to rehydrate campaign {c.id}: {e}")
#     except Exception as e:
#         print(f"[campaign scheduler] Startup rehydration error: {e}")

# # Intake worker lifecycle (unchanged)
# app.add_event_handler("startup", start_scheduler(app))
# app.add_event_handler("shutdown", stop_scheduler(app))


# _stop_event: asyncio.Event | None = None
# _task: asyncio.Task | None = None

# # ======= Startup: general scheduler + campaign reschedule =======
# @app.on_event("startup")
# async def _startup_general():
#     get_scheduler()
#     await reschedule_campaigns_on_startup()
#     # start the ALWAYS-ON texting daemon loops (scheduled + unscheduled)
#     try:
#         tz = os.getenv("APS_TIMEZONE", "UTC")
#         schedule_texting_job(tz)   # nudges loops + periodic keepalive nudges
#     except Exception as e:
#         print("[text scheduler] failed to schedule texting job:", e)

# # Optionally trigger an immediate tick once on boot (doesn't block startup)
# @app.on_event("startup")
# async def _kickoff_text_jobs():
#     try:
#         from controllers.text_assistant_controller import run_texting_job, run_unscheduled_texting_job
#         asyncio.create_task(run_texting_job())
#         asyncio.create_task(run_unscheduled_texting_job())
#         print("[text scheduler] kickoff: triggered scheduled & unscheduled texting jobs")
#     except Exception as e:
#         print("[text scheduler] kickoff error:", e)

# # ======= Shutdown: campaign scheduler =======
# @app.on_event("shutdown")
# async def _shutdown_schedulers():
#     shutdown_scheduler(wait=False)
    
    

# @app.on_event("startup")
# async def _startup():
#     global _stop_event, _task
#     _stop_event = asyncio.Event()
#     _task = asyncio.create_task(run_interest_scheduler(_stop_event))

# @app.on_event("shutdown")
# async def _shutdown():
#     global _stop_event, _task
#     if _stop_event:
#         _stop_event.set()
#     if _task:
#         try:
#             await asyncio.wait_for(_task, timeout=5)
#         except Exception:
#             pass
# @app.on_event("startup")
# async def _on_startup():
   
#     start_scheduler()

# @app.on_event("shutdown")
# async def _on_shutdown():
#     await stop_scheduler()# main.py
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
from controllers.intake_admin import router as intake_admin_router
from controllers.facebook_leads_controller import router as facebook_router
from controllers.stripe_controller import router as stripe_controller
from controllers.calldetails_controller import router as call_details
from controllers.text_assistant_controller import router as text_assistant_router
from controllers.admin_billing import router as admin_payment_controls
from controllers.vapi_server_url import router as vapi_server_url
from controllers.Calendar_controller import router as CalenderController

from helpers.interest_scheduler import run_interest_scheduler

# Intake worker scheduler (already in your codebase)
from helpers.intake_worker import (
    start_scheduler as start_intake_scheduler,
    stop_scheduler as stop_intake_scheduler,
)

# NEW: appointment auto-extraction scheduler
from helpers.appointment_scheduler import (
    start_scheduler as start_appt_scheduler,
    stop_scheduler as stop_appt_scheduler,
)

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
app.include_router(facebook_router, prefix="/api", tags=["Facebook Routes"])
app.include_router(text_assistant_router, prefix="/api", tags=["Text Assistant Controller"])
app.include_router(vapi_server_url, prefix="/api")
app.include_router(stripe_controller, prefix="/api", tags={"Stripe Controller"})
app.include_router(CalenderController, prefix="/api", tags={"Calender Controller"})
app.include_router(call_details, prefix="/api", tags={"User Call Logs"})
app.include_router(admin_payment_controls, prefix="/api", tags={"admin payment controls"})

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

# Intake worker lifecycle (keep your existing pattern that expects `app`)
# NOTE: start_intake_scheduler(app) returns a callable/coro per your implementation.
app.add_event_handler("startup", start_intake_scheduler(app))
app.add_event_handler("shutdown", stop_intake_scheduler(app))

# ======= Startup: general scheduler + campaign reschedule =======
@app.on_event("startup")
async def _startup_general():
    # APS for campaigns + reschedule persisted jobs
    get_scheduler()
    await reschedule_campaigns_on_startup()

    # Schedule texting job safely (import inside so missing symbol won’t crash)
    try:
        from controllers.text_assistant_controller import schedule_texting_job
        tz = os.getenv("APS_TIMEZONE", "UTC")
        schedule_texting_job(tz)
    except Exception as e:
        print("[text scheduler] schedule_texting_job not started:", e)

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

# ======= Interest scheduler (your existing one) =======
_interest_stop: asyncio.Event | None = None
_interest_task: asyncio.Task | None = None

@app.on_event("startup")
async def _interest_startup():
    global _interest_stop, _interest_task
    _interest_stop = asyncio.Event()
    _interest_task = asyncio.create_task(run_interest_scheduler(_interest_stop))

@app.on_event("shutdown")
async def _interest_shutdown():
    global _interest_stop, _interest_task
    if _interest_stop:
        _interest_stop.set()
    if _interest_task:
        try:
            await asyncio.wait_for(_interest_task, timeout=5)
        except Exception:
            pass

# ======= Appointment auto-extraction scheduler (NEW) =======
@app.on_event("startup")
async def _appointments_scheduler_start():
    try:
        start_appt_scheduler()
        print("[appointments] auto-extraction scheduler started")
    except Exception as e:
        print("[appointments] scheduler start error:", e)

@app.on_event("shutdown")
async def _appointments_scheduler_stop():
    try:
        await stop_appt_scheduler()
        print("[appointments] auto-extraction scheduler stopped")
    except Exception as e:
        print("[appointments] scheduler stop error:", e)

# ======= Shutdown: campaign scheduler =======
@app.on_event("shutdown")
async def _shutdown_campaings():
    shutdown_scheduler(wait=False)
