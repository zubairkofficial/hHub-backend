from tortoise import fields, models

class LeadScore(models.Model):
    id = fields.IntField(pk=True)
    client_id = fields.CharField(max_length=255, null=False)
    callrail_id = fields.CharField(max_length=255)
    analysis_summary = fields.TextField(null=True)
    created_at = fields.DatetimeField(null=True)
    updated_at = fields.DatetimeField(null=True)
    deleted_at = fields.DatetimeField(null=True)
    tone_score = fields.FloatField(null=True)
    intent_score = fields.FloatField(null=True)
    urgency_score = fields.FloatField(null=True)
    overall_score = fields.FloatField(null=True)

    class Meta:
        table = "lead_score"
        ordering = ["-overall_score"]
        