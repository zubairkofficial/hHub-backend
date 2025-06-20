from tortoise import Tortoise
import os
import dotenv
from models.job_tracker import JobTracker

dotenv.load_dotenv()

TORTOISE_CONFIG = {
    'connections': {
        'default': os.getenv('DATABASE_URL')
    },
    'apps': {
        'models': {
            'models': [
                'aerich.models',
                'models.model',
                'models.lead_score',
                'models.followup_prediction',
                'models.chat_history',
                'models.chat',
                'models.message',
                'models.system_prompt',
                'models.job_tracker'
            ],
            'default_connection': 'default'
        },
    },
}

async def lifespan(_):
    await Tortoise.init(config=TORTOISE_CONFIG)
    await Tortoise.generate_schemas()
    print("Initializing LifeSpan")
    yield

    