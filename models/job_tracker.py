# models/job_tracker.py
from tortoise import fields
from tortoise.models import Model
from dotenv import load_dotenv 

load_dotenv()


class JobTracker(Model):
    id = fields.IntField(pk=True)
    job_name = fields.CharField(max_length=255)
    last_run_time = fields.DatetimeField(auto_now=True)  # Automatically updated whenever the record is saved
