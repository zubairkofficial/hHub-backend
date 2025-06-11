from tortoise import fields, models

class ChatModel(models.Model):
    id = fields.IntField(pk=True)
    user_id = fields.CharField(max_length=100)
    title = fields.CharField(max_length=255, default="New Chat")
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)