from tortoise import fields, models

class Message(models.Model):
    id = fields.IntField(pk=True)
    user_id = fields.CharField(max_length=100)
    chat_id = fields.IntField()
    user_message = fields.TextField()
    bot_response = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)

  