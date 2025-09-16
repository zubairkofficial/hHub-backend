# helper/CallRailProcessor.py

import httpx
import json
import logging
from typing import List, Dict, Any, Optional

class CallRailProcessor:
    """Process CallRail data and manage client leads (HTTP helpers for Laravel)."""

    def __init__(self, api_url: str, headers: dict):
        self.api_url = (api_url or "").rstrip("/")
        self.headers = headers
        self.logger = logging.getLogger("cron_job.callrail_processor")

    # --- optional legacy path (keep if you still use it elsewhere) ---
    async def process_clients(self, client_ids: List[str], user_id: int, callrail_id: Optional[str] = None) -> dict:
        try:
            self.logger.info("=== Starting client processing ===")
            self.logger.info(f"User ID: {user_id}")
            self.logger.info(f"Client IDs: {client_ids}")
            if callrail_id:
                self.logger.info(f"Filtering by CallRail ID: {callrail_id}")

            client_ids = [str(cid).strip() for cid in client_ids if str(cid).strip()]
            if not client_ids:
                return {"status": "error", "detail": "No client IDs provided"}

            records = await self._fetch_callrail_records(user_id, client_ids, callrail_id)
            if not records:
                self.logger.warning("No CallRail records found")
                return {"status": "success", "detail": "No records found", "processed_count": 0}

            records = self._dedupe_records(records)
            payloads, skipped = [], 0
            for r in records:
                try:
                    p = self._build_lead_payload(r, user_id)
                    if not p.get("contact_number") or not p.get("type"):
                        skipped += 1
                        self.logger.debug(f"Skipping: missing required fields -> {p}")
                        continue
                    payloads.append(p)
                except Exception as e:
                    skipped += 1
                    self.logger.warning(f"Skipping malformed record: {e}")

            if not payloads:
                self.logger.info(f"No valid records to send (skipped={skipped})")
                return {"status": "success", "detail": "No valid records", "processed_count": 0}

            save_result = await self._batch_save_leads(payloads)

            created = save_result.get("created", []) or []
            updated = save_result.get("updated", []) or []
            errors  = save_result.get("errors", {}) or {}
            status  = save_result.get("status", "unknown")

            self.logger.info("=== Processing Complete ===")
            self.logger.info(f"Total input records: {len(records)}")
            self.logger.info(f"Valid to send: {len(payloads)}, Skipped locally: {skipped}")
            self.logger.info(f"Created: {len(created)} | Updated: {len(updated)} | Errors: {len(errors)}")

            return {
                "status": status,
                "processed_count": len(payloads),
                "created_count": len(created),
                "updated_count": len(updated),
                "error_count": len(errors),
                "created": created,
                "updated": updated,
                "errors": errors,
            }
        except Exception as e:
            self.logger.error(f"Error in process_clients: {str(e)}", exc_info=True)
            return {"status": "error", "message": str(e)}

    async def _fetch_callrail_records(self, user_id: int, client_ids: List[str], callrail_id: Optional[str]) -> List[dict]:
        """Fetch CallRail records from Laravel transcript API."""
        try:
            params = {
                "client_ids": ",".join(client_ids),
                "include_processed": "true",  # get both; filter elsewhere if needed
            }
            if callrail_id:
                params["callrail_id"] = callrail_id

            url = f"{self.api_url}/api/transcript/{user_id}"
            async with httpx.AsyncClient(timeout=30) as client:
                self.logger.debug(f"GET {url} params={params}")
                resp = await client.get(url, params=params, headers=self.headers)
                text = resp.text
                try:
                    data = resp.json()
                except Exception:
                    self.logger.error(f"Transcript API non-JSON: {text[:500]}")
                    resp.raise_for_status()
                    return []

                if resp.status_code >= 400:
                    self.logger.error(f"Transcript API HTTP {resp.status_code}: {text[:500]}")
                    return []

                if not data.get("success", False):
                    self.logger.error(f"Transcript API error: {data}")
                    return []

                return data.get("data", []) or []
        except Exception as e:
            self.logger.error(f"Error fetching CallRail records: {str(e)}", exc_info=True)
            return []

    def _dedupe_records(self, records: List[dict]) -> List[dict]:
        """Deduplicate by call id, else by (phone, date)."""
        seen = set()
        out = []
        for r in records:
            key = r.get("id") or (
                (r.get("phone_number") or r.get("caller_phone_number")),
                (r.get("date") or r.get("created_at")),
            )
            if key and key not in seen:
                seen.add(key)
                out.append(r)
        return out

    def _infer_type(self, record: dict) -> str:
        """Infer Laravel 'type': 'receive' if duration>0 and not missed, else 'miss'."""
        duration = record.get("duration")
        status = str(record.get("status") or record.get("call_status") or "").lower()
        if duration in (0, None) or status in ("missed", "no-answer", "busy", "failed"):
            return "miss"
        return "receive"

    def _build_lead_payload(self, record: dict, user_id: int) -> dict:
        """
        Map CallRail record -> Laravel /api/save-client-lead item.
        REQUIRED by Laravel: contact_number, type, user_id.
        """
        phone = (record.get("phone_number") or record.get("caller_phone_number") or "").strip()
        call_type = self._infer_type(record)

        meta = {
            "callrail_id": record.get("callrail_id"),
            "call_id": record.get("id"),
            "recording_url": record.get("recording_url"),
            "duration": record.get("duration"),
            "call_date": record.get("date") or record.get("created_at"),
            "caller_name": record.get("name"),
            "city": record.get("city"),
            "state": record.get("state"),
            "country": record.get("country"),
            "source_type_raw": record.get("source_type"),
        }
        description = json.dumps({k: v for k, v in meta.items() if v not in ("", None, [])})

        item = {
            "user_id": user_id,
            "contact_number": phone,
            "type": call_type,  # 'receive' or 'miss'
            "first_name": record.get("name") or None,
            "email": record.get("email") or None,
            "booking_id": record.get("booking_id") or None,
            "callrail_id": record.get("callrail_id"),
            "description": description,
            "status": "new",
            "potential_score": record.get("score"),
            "transcription": record.get("transcription"),
            "is_scored": True,
            "is_self": False,
        }
        return {k: v for k, v in item.items() if v not in ("", None, [])}

    async def _batch_save_leads(self, payloads: List[dict]) -> dict:
        """POST array of items to /api/save-client-lead (legacy path)."""
        url = f"{self.api_url}/api/save-client-lead"
        async with httpx.AsyncClient(timeout=60) as client:
            self.logger.debug(f"POST {url} count={len(payloads)}")
            resp = await client.post(url, json=payloads, headers=self.headers)
            text = resp.text
            try:
                data = resp.json()
            except Exception:
                self.logger.error(f"Save leads non-JSON: {text[:1000]}")
                resp.raise_for_status()
                raise Exception(f"Save leads failed: HTTP {resp.status_code}")

            if resp.status_code >= 400:
                raise Exception(f"HTTP {resp.status_code}: {data}")

            status = (data.get("status") or "").lower()
            if status in ("success", "partial"):
                return data

            raise Exception(data.get("message") or "Failed to save client leads")

    # *** THIS IS THE METHOD YOUR HELPER CALLS ***
    async def _send_processed_data_to_laravel(self, data_to_send: List[Dict[str, Any]], user_id: int) -> dict:
        """
        POST an array of items to /api/save-client-lead.
        Controller accepts single object or array; we send an array.
        Returns Laravel's JSON dict: {status, created, updated, errors}
        """
        url = f"{self.api_url}/api/save-client-lead"

        # Ensure every item has user_id & strip empties
        payload = []
        for item in (data_to_send or []):
            it = dict(item or {})
            it.setdefault("user_id", user_id)
            clean = {k: v for k, v in it.items() if v not in ("", None, [])}
            payload.append(clean)

        if not payload:
            self.logger.info("No payload items to send to Laravel")
            return {"status": "success", "created": [], "updated": [], "errors": {}}

        self.logger.info(
            "POST /save-client-lead count=%d example=%s",
            len(payload),
            {k: payload[0].get(k) for k in ("contact_number", "type")}
        )

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, json=payload, headers=self.headers)
            text = resp.text
            try:
                data = resp.json()
            except Exception:
                self.logger.error("save-client-lead non-JSON: %s", text[:1000])
                resp.raise_for_status()
                return {"status": "error", "body": text}

            if resp.status_code >= 400:
                self.logger.error("save-client-lead HTTP %s: %s", resp.status_code, data)
                return {"status": "error", "body": data}

            # {status: 'success'|'partial'|'error', created:[], updated:[], errors:{}}
            return data
