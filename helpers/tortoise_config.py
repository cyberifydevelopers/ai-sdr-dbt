from tortoise import Tortoise
import os
from dotenv import load_dotenv

load_dotenv()

TORTOISE_CONFIG = {
    'connections': {
        'default': os.getenv("DATABASE_URL")
    },
    "apps": {
        "models": {
            "models": [
                "models.auth",
                "aerich.models",
                "models.purchased_numbers",
                "models.assistant",
                "models.call_log",
                "models.file",
                "models.lead",
                "models.documents",
                "models.campaign",
                "models.crm",
                "models.appointment"
            ]
        }
    }
    }



async def lifespan(_):
    await Tortoise.init(config=TORTOISE_CONFIG)
    yield
    
    
