from tortoise import fields, models

class PostPromptSettings(models.Model):
    id = fields.IntField(pk=True)
    post_prompt = fields.TextField(null=True)
    idea_prompt = fields.TextField(null=True)
    image_prompt = fields.TextField(null=True)
    fal_ai_api_key = fields.TextField(null=True)
    openai_api_key = fields.TextField(null=True)
    gemini_api_key = fields.TextField(null=True)  # ← already added
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "post_prompt_settings" 