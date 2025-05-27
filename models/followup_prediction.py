from tortoise import fields, models

class FollowupPrediction(models.Model):
    id = fields.IntField(pk=True)
    client_id = fields.IntField(null=True)
    predicted_followup_time = fields.DatetimeField(null=True)

    class Meta:
        table = "followup_prediction"
