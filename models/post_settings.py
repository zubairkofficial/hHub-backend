from tortoise import fields, models

class PostSettings(models.Model):
    id = fields.IntField(pk=True)
    business_idea = fields.TextField()
    brand_guidelines = fields.TextField(null=True)
    frequency = fields.CharField(max_length=32, default='daily')
    posts_per_period = fields.IntField(default=1) 
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "post_settings" 