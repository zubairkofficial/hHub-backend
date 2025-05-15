from tortoise import Tortoise
import os
import dotenv

dotenv.load_dotenv()
DATABASE_URL = os.environ['DATABASE_URL']

TORTOISE_CONFIG = {
    'connections': {
        'default': "mysql://admin:password@localhost:3306/h_hub"
    },
    'apps': {
        'models': {
            'models': [
                'aerich.models',
                'models.model',
                'models.lead_score'
            ],
            'default_connection': 'default'
        },
    },
}

async def lifespan(_):
    await Tortoise.init(config=TORTOISE_CONFIG)
    print("Initializing LifeSpan")
    yield

    