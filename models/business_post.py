from tortoise import fields, models

class BusinessPost(models.Model):
    id = fields.IntField(pk=True)
    post = fields.TextField(null=True)
    scheduled_time = fields.DatetimeField(null=True)
    status = fields.CharField(max_length=32, default='scheduled')
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "business_post" 