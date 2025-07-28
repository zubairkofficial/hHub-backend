from tortoise import fields, models

class PostSettings(models.Model):
    id = fields.IntField(pk=True)
    user_id = fields.CharField(max_length=100)
    business_idea = fields.TextField()
    brand_guidelines = fields.TextField(null=True)
    frequency = fields.CharField(max_length=32, default='daily')
    posts_per_period = fields.IntField(default=1) 
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    weekly_days = fields.JSONField(null=True)  # e.g., ["Monday", "Wednesday"]
    monthly_dates = fields.JSONField(null=True)  # e.g., ["2024-07-05", "2024-07-12"]
    uploaded_file = fields.CharField(max_length=255, null=True)  # Stores the uploaded file name or path
    extracted_file_text = fields.TextField(null=True)  # Stores all extracted text from uploaded file
    reference_images = fields.JSONField(null=True)  # List of reference image data with full analysis (up to 10 images)

    class Meta:
        table = "post_settings" 