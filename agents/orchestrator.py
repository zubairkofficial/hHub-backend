# agents/orchestrator.py

import json
from typing import Any, Dict, List, Optional

from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import ToolMessage

from agents.registry import get_agent, REGISTRY
from agents.router import pick_agent
from helper.chat_context import get_chat_history

from agents.tools.helpers.parsing import (
    EMAIL_RE, PHONE_RE,
    parse_lead_id, parse_clinic_id,
    UPDATE_CLINIC_NAME_TO,
    UPDATE_CLINIC_NAME_FREEFORM,
    UPDATE_CLINIC_NAME_POSSESSIVE_TO,
    UPDATE_CLINIC_NAME_OF_TO,
    UPDATE_CLINIC_RENAME_FROM_TO,
    UPDATE_CLINIC_CURRENT_NEW,
)

from agents.tools.helpers.logging import ai_dbg
from agents.tools.helpers.formatting import fmt_lead_details, fmt_clinic_details
from agents.tools.helpers.security import get_client_id, enforce_client_id, remember_client_id
from agents.fastpaths.leads import fastpath_fetch_lead_by_id, fastpath_search_leads, fastpath_update_lead
from agents.fastpaths.clinics import fastpath_update_clinic
from agents.tools.http_clinics import clinic_get_http

def _json(o: Any) -> str:
    return json.dumps(o, ensure_ascii=False, default=str)

APP_ONLY_HINT = (
    "I can only help with Houmanity leads/clinics. "
    "Please include a lead id, clinic id, phone, email, or a clear update command."
)

async def run_with_agent(user_message: str, chat_id: int, user_id: str) -> str:
    ai_dbg("chat.incoming", {"user_id": user_id, "chat_id": chat_id, "user_message": user_message})
    msg = (user_message or "").strip()

    # tenancy
    client_id_val = await get_client_id(user_id)
    ai_dbg("user.client_id", client_id_val)
    ai_dbg("clinic.fastpath.precheck", {"client_id_val": client_id_val, "msg": msg[:120]})
    remember_client_id(user_id, client_id_val)

    # parse hints — do this FIRST
    lead_id_req   = parse_lead_id(msg)
    clinic_id_req = parse_clinic_id(msg)
    em = EMAIL_RE.search(msg)
    ph = PHONE_RE.search(msg)
    email_hint = em.group(0) if em else None
    phone_hint = ph.group(0) if ph else None
    ai_dbg("parsed.hints", {
        "lead_id_req": lead_id_req, "clinic_id_req": clinic_id_req,
        "email_hint": email_hint, "phone_hint": phone_hint
    })

    # clinic rename intent (for special casing)
    intent_rename = any((
        UPDATE_CLINIC_NAME_TO.search(msg),
        UPDATE_CLINIC_NAME_FREEFORM.search(msg),
        UPDATE_CLINIC_NAME_POSSESSIVE_TO.search(msg),
        UPDATE_CLINIC_NAME_OF_TO.search(msg),
        UPDATE_CLINIC_RENAME_FROM_TO.search(msg),
        UPDATE_CLINIC_CURRENT_NEW.search(msg),
    ))
    if client_id_val is None and intent_rename:
        return ("I can’t update your clinic because this session isn’t linked to a client. "
                "Please sign in, then try again.")
    if client_id_val is None and (lead_id_req is not None or clinic_id_req is not None or email_hint or phone_hint):
        return ("I can’t access lead or clinic data because your account isn’t linked to a client yet. "
                "Please sign in or ensure your user has a client_id assigned.")
    if intent_rename:
        clinic_id_req = None

    # 1) clinic update fast-path (run BEFORE any fetch)
    upd = await fastpath_update_clinic(msg, client_id_val)
    if upd is not None:
        ai_dbg("clinic.update.return", upd[:300].replace("\n", " | "))
        return upd

    # 1b) lead update fast-path
    upd_lead = await fastpath_update_lead(msg, client_id_val)
    if upd_lead is not None:
        ai_dbg("lead.update.return", upd_lead[:300].replace("\n", " | "))
        return upd_lead

    # 2) fetch fast-path
    async def _fastpath_fetch() -> Optional[str]:
        if client_id_val is None:
            ai_dbg("fastpath.skip", "no client_id")
            return None

        # A) Lead by id
        if lead_id_req is not None:
            return await fastpath_fetch_lead_by_id(client_id_val, lead_id_req, phone_hint, email_hint)

        # B) Clinic by id
        if clinic_id_req is not None:
            try:
                args_c = {"client_id": client_id_val, "clinic_id": clinic_id_req}
                ai_dbg("fastpath.clinic_get.args", args_c)
                rawc = await clinic_get_http.ainvoke(args_c)
                ai_dbg("fastpath.clinic_get.raw", (rawc[:500] if isinstance(rawc, str) else str(rawc)[:500]))
                dc = json.loads(rawc) if isinstance(rawc, str) else rawc
            except Exception as e:
                ai_dbg("fastpath.clinic_get.error", repr(e))
                dc = {"ok": False}

            if dc.get("ok") and dc.get("clinic"):
                clinic = dc["clinic"]
                return f"Clinic #{clinic_id_req} details:\n" + fmt_clinic_details(clinic)
            return f"Clinic #{clinic_id_req} not found for your account."

        # C) Lead search by email/phone
        if email_hint or phone_hint:
            return await fastpath_search_leads(client_id_val, phone_hint, email_hint, lead_id_req)

        ai_dbg("fastpath.skip", "no id/email/phone hints")
        return None

    fast = await _fastpath_fetch()
    if fast is not None:
        ai_dbg("fastpath.return", fast[:300].replace("\n", " | "))
        return fast

    # 3) Tool-driven agent path (NO generic fallback)
    # Decide a safe agent; never SmallTalk.
    try:
        # Prefer SQLReader when we have explicit ids/hints, else use router.
        agent_name = "SQLReader" if (lead_id_req or clinic_id_req or email_hint or phone_hint) else (await pick_agent(user_message))["agent"]
    except Exception:
        # If router fails, still stay in-app — choose SQLReader (tooling only)
        agent_name = "SQLReader"

    # Enforce registry fallback without SmallTalk
    spec = get_agent(agent_name) if agent_name in REGISTRY else get_agent("SQLReader")
    ai_dbg("agent.selected", {"agent": spec.name})

    # Bind only tools; we never use free-form LLM output as final content.
    model = init_chat_model("gpt-4o-mini", model_provider="openai")
    if getattr(spec, "allow_tool_calls", True) and spec.tools:
        model = model.bind_tools(spec.tools)
    ai_dbg("agent.tools", {"tools": [t.name for t in (spec.tools or [])]})

    history = await get_chat_history(chat_id)
    sys_prompt = spec.system_prompt
    if client_id_val is not None and spec.name in ("SQLReader", "LeadAgent", "ClinicAgent"):
        sys_prompt = f"{sys_prompt}\n[SECURITY NOTE] Current client_id={client_id_val}. All operations must include client_id={client_id_val}."

    prompt = ChatPromptTemplate.from_messages([
        ("system", sys_prompt),
        MessagesPlaceholder("history"),
        ("user", "{prompt}"),
    ])
    rendered = await prompt.ainvoke({"history": history, "prompt": user_message})
    messages = rendered.to_messages()

    ai_msg = await model.ainvoke(messages)
    tool_calls = getattr(ai_msg, "tool_calls", None) or []
    ai_dbg("agent.tool_calls", {"tool_calls": tool_calls})

    # If no tool calls AND we had fetch intent -> give deterministic app hint, not generic text.
    if not tool_calls:
        ai_dbg("agent.no_tools", "no tool calls produced; returning app-only hint")
        return APP_ONLY_HINT

    followups: List[Any] = [ai_msg]
    name_to_fn = {t.name: t for t in (spec.tools or [])}
    fetched_lead: Optional[Dict[str, Any]] = None
    fetched_clinic: Optional[Dict[str, Any]] = None
    searched_rows: List[Dict[str, Any]] = []
    lead_updated_id: Optional[int] = None

    for tc in tool_calls:
        name = tc.get("name")
        args = tc.get("args", {}) or {}
        try:
            safe_args = enforce_client_id(name, args, client_id_val)
            ai_dbg("tool.call", {"name": name, "args": safe_args})
            result = await name_to_fn[name].ainvoke(safe_args)
            ai_dbg("tool.result", (result[:500] if isinstance(result, str) else str(result)[:500]))
            data = json.loads(result) if isinstance(result, str) else result

            if name in ("lead_get", "lead_get_http"):
                if isinstance(data, dict) and data.get("ok") and data.get("lead"):
                    fetched_lead = data["lead"]
            elif name in ("clinic_get", "clinic_get_http"):
                if isinstance(data, dict) and data.get("ok") and data.get("clinic"):
                    fetched_clinic = data["clinic"]
            elif name == "lead_search":
                if isinstance(data, dict) and data.get("ok") and isinstance(data.get("rows"), list):
                    searched_rows = data["rows"]
            elif name in ("lead_update_http", "update_lead"):
                # capture updated id if present in args
                lead_updated_id = safe_args.get("lead_id") or lead_updated_id
                # if API echoes updated lead, we could read ok flag directly
                if isinstance(data, dict) and data.get("ok"):
                    return f"Lead #{lead_updated_id or '—'} updated successfully."

            result_str = _json({"ok": True, "tool": name, "args_used": safe_args, "result": result})
        except Exception as e:
            ai_dbg("tool.error", {name: repr(e)})
            result_str = _json({"ok": False, "tool": name, "error": f"{e.__class__.__name__}: {e}"})
        followups.append(ToolMessage(content=result_str, tool_call_id=tc["id"]))

    # Deterministic returns only — no generic LLM prose
    if fetched_lead:
        if phone_hint and (fetched_lead.get("contact_number") or "").strip() != (phone_hint or "").strip():
            return "No access or unauthorized for this lead."
        if email_hint and (fetched_lead.get("email") or "").strip().lower() != (email_hint or "").strip().lower():
            return "No access or unauthorized for this lead."
        return f"Lead #{fetched_lead['id']} details:\n" + fmt_lead_details(fetched_lead)

    if fetched_clinic:
        return f"Clinic details:\n" + fmt_clinic_details(fetched_clinic)

    if searched_rows:
        lines = [
            f"• #{r['id']}: {r.get('first_name','')} {r.get('last_name','')} — {r.get('email','—')} — {r.get('contact_number','—')} — {r.get('status','—')}"
            for r in searched_rows[:10]
        ]
        return "Matches:\n" + "\n".join(lines)

    # If tools ran but no explicit reply and we updated a lead, return a clear success
    if lead_updated_id:
        return f"Lead #{lead_updated_id} updated successfully."

    # Final guard: keep it app-only
    return APP_ONLY_HINT
