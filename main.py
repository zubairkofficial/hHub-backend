from fastapi import FastAPI
from helper.tortoise_config import lifespan

app = FastAPI(lifespan=lifespan)

app.get('/')
def default_api():
    return "Hello to the world of AI"

