from agents.registry import AgentSpec, register
from helper.tools.lead_tools import update_lead
from agents.tools.http_leads import lead_get_http
from agents.tools.sql_tools import sql_select, lead_get, lead_search
from agents.registry import REGISTRY
from agents.tools.http_clinics import clinic_get_http, clinic_search_http, clinic_update


MAIN_MODEL = "gpt-4o-mini"

# ✅ LeadAgent (ENABLE tool calls)
register(AgentSpec(
    name="LeadAgent",
    system_prompt=(
        "You are LeadAgent. You update and enrich CRM leads. "
        "When user asks to change a lead, call update_lead with minimal, exact fields. "
        "Never guess IDs; ask for a phone/email/name to lookup if lead_id is missing."
    ),
    tools=[update_lead],             # <- important
    # allow_tool_calls defaults to True in our AgentSpec; if not, set allow_tool_calls=True here
))

# ✅ SQLReader for fetching
register(AgentSpec(
    name="SQLReader",
    system_prompt=(
        "You are SQLReader. Use lead_get / lead_search / sql_select to fetch data. "
        "Always enforce client ownership by including the client's client_id in the call. "
        "Prefer lead_get for a single known ID; use lead_search for name/email/phone; "
        "only fall back to generic sql_select when truly necessary."
    ),
    tools=[lead_get_http, lead_get, lead_search, sql_select],
))

register(AgentSpec(
    name="ReminderAgent",
    system_prompt=(
        "You are ReminderAgent. You schedule reminders or send notifications to the user via backend services."
        "Use dedicated service wrappers (create_reminder/push_notification) exposed by orchestrator tools."
    ),
    tools=[],
))



# before using get_agent(...)
if "SmallTalk" not in REGISTRY:
    register(AgentSpec(
        name="SmallTalk",
        system_prompt=(
            "You are a friendly assistant. If the system message includes [USER CONTEXT], "
            "use it to answer personal/profile questions only when explicitly asked. Avoid tools."
        ),
        tools=[],
        allow_tool_calls=False,
    ))

register(AgentSpec(
    name="ClinicAgent",
    system_prompt=(
        "You are ClinicAgent. You fetch and update Clinic records.\n"
        "Use clinic_get_http / clinic_search_http to read; use clinic_update for changes.\n"
        "Always include the enforced client_id (provided by the system)."
    ),
    tools=[clinic_get_http, clinic_search_http, clinic_update],
))