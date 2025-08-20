from tortoise import Tortoise
import os
import dotenv

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
                'models.job_tracker',
                'models.business_post',
                'models.post_settings',
                'models.post_draft',
                'models.post_prompt_settings',
                'models.image_settings',
                'models.image_generation_setting',
                'models.post_history',
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

    