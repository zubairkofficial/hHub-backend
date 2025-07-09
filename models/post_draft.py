from tortoise import fields, models

class PostDraft(models.Model):
    id = fields.IntField(pk=True)
    user_id = fields.CharField(max_length=100)
    current_step = fields.IntField(default=1)  # 1-5
    content = fields.TextField(null=True)      # Step 1
    keywords = fields.JSONField(null=True)     # Step 2
    post_options = fields.JSONField(null=True) # List of generated post texts (step 3)
    selected_post_index = fields.IntField(null=True) # Which post was selected
    image_ids = fields.JSONField(null=True)    # List of image ids (uploaded or generated) for each post option
    selected_image_id = fields.TextField(null=True)  # Final image
    is_complete = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "post_draft" 