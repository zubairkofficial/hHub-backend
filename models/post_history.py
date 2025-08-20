from tortoise import Tortoise, fields, Model
from enum import Enum
class PageTypeEnum(str, Enum):
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"

class PostHistory(Model):
    id = fields.IntField(pk=True)
    user_id = fields.IntField()  # Assuming you still want a direct user ID
    post_draft = fields.ForeignKeyField('models.PostDraft', related_name='post_histories')  # Foreign key to PostDraft
    page_name = fields.CharField(max_length=255)  
    page_type = fields.CharEnumField(PageTypeEnum)  # Enum for page type
    status= fields.CharField(max_length=255,null=True)
    message= fields.CharField(max_length=255,null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "post_history"