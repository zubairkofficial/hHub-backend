from tortoise import fields, models

class ImageGenerationSetting(models.Model):
    id = fields.IntField(pk=True)
    num_images = fields.IntField(default=1)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "image_generation_setting" 