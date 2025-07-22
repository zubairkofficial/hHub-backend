from tortoise import fields, models

class PostDraft(models.Model):
    id = fields.IntField(pk=True)
    user_id = fields.CharField(max_length=100)
    current_step = fields.IntField(default=1) 
    content = fields.TextField(null=True)
    title = fields.CharField(max_length=255, null=True)
    description = fields.TextField(null=True)
    keywords = fields.JSONField(null=True)    
    post_options = fields.JSONField(null=True) 
    selected_post_index = fields.IntField(null=True) 
    image_ids = fields.JSONField(null=True)
    status = fields.CharField(max_length=32, default='draft')
    selected_image_id = fields.TextField(null=True) 
    is_complete = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    posted_at = fields.DatetimeField(null=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "post_draft" 