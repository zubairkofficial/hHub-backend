from tortoise import fields
from tortoise.models import Model
from datetime import datetime

class SystemPrompts(Model):
    id = fields.IntField(pk=True)
    system_prompt = fields.TextField()
    analytics_prompt = fields.TextField()
    summery_score = fields.TextField()
    hour = fields.TextField(defualt="1",null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "system_prompts"
