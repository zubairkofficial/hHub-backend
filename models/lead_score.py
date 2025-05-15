from tortoise import fields, models

class LeadScore(models.Model):
    id = fields.IntField(pk=True)
    call_id = fields.CharField(max_length=255)
    call_recording = fields.TextField(null=True)
    name = fields.CharField(max_length=255, null=True)
    date = fields.DatetimeField(null=True)
    source_type = fields.CharField(max_length=255, null=True)
    phone_number = fields.CharField(max_length=50, null=True)
    duration = fields.IntField(null=True)
    country = fields.CharField(max_length=10, null=True)
    state = fields.CharField(max_length=10, null=True)
    city = fields.CharField(max_length=100, null=True)
    answer = fields.IntField(null=True)
    first_call = fields.IntField(null=True)
    lead_status = fields.IntField(null=True)
    call_highlight = fields.IntField(null=True)
    transcription = fields.TextField(null=True)
    note = fields.TextField(null=True)
    created_at = fields.DatetimeField(null=True)
    updated_at = fields.DatetimeField(null=True)
    deleted_at = fields.DatetimeField(null=True)
    tone_score = fields.FloatField(null=True)
    intent_score = fields.FloatField(null=True)
    urgency_score = fields.FloatField(null=True)
    overall_score = fields.FloatField(null=True)
    priority = fields.CharField(max_length=50, null=True)
    priority_level = fields.IntField(null=True)

    class Meta:
        table = "lead_score" 