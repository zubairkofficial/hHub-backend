# models/agent_run.py
from tortoise import fields, models

class AgentRun(models.Model):
    id = fields.IntField(pk=True)
    chat_id = fields.IntField()
    user_id = fields.CharField(max_length=191)
    agent = fields.CharField(max_length=64)
    router_confidence = fields.FloatField(null=True)
    user_message = fields.TextField()
    final_reply = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "agent_runs"   # <— explicit

class ToolEvent(models.Model):
    id = fields.IntField(pk=True)
    run: fields.ForeignKeyRelation[AgentRun] = fields.ForeignKeyField(
        "models.AgentRun", related_name="tool_events"
    )
    tool_name = fields.CharField(max_length=64)
    args_json = fields.TextField(null=True)
    result_json = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "tool_events"  # <— explicit
