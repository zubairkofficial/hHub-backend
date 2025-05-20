from tortoise import fields, models

class LeadScore(models.Model):
    id = fields.IntField(pk=True)
    client_id = fields.CharField(max_length=255, null=True)
    callrail_id = fields.CharField(max_length=255, null=True)
    analysis_summary = fields.TextField(null=True)
    created_at = fields.DatetimeField(null=True)
    updated_at = fields.DatetimeField(null=True)
    deleted_at = fields.DatetimeField(null=True)
    intent_score = fields.FloatField(null=True)
    urgency_score = fields.FloatField(null=True)
    overall_score = fields.FloatField(null=True)

    class Meta:
        table = "lead_score"
        ordering = ["-overall_score"]
        