from tortoise import fields, models

class ImageSettings(models.Model):
    id = fields.IntField(pk=True)
    user_id = fields.CharField(max_length=100)
    image_type = fields.CharField(max_length=32)
    image_design = fields.CharField(max_length=32)
    instruction = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "image_settings" 