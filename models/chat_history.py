from tortoise import fields, models

class ChatHistory(models.Model):
    id = fields.IntField(pk=True)
    user_message = fields.TextField()
    bot_response = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "chat_history" 