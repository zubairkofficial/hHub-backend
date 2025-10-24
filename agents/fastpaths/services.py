# agents/fastpaths/services.py
import re
from typing import Optional, Dict

# e.g. "update service 7 name to Whitening"
UPDATE_SERVICE_SIMPLE = re.compile(
    r"(?:update|change|set)\s+service\s*(?:id|#)?\s*(\d{1,10})\s+"
    r"(name|description|for_report)"
    r"(?:\s*(?:to|=|as)\s*|\s+to\s+)\s*['\"]?([^'\"\n\r]+?)['\"]?\s*$",
    re.IGNORECASE,
)

def parse_service_update(msg: str) -> Optional[Dict]:
    m = UPDATE_SERVICE_SIMPLE.search(msg or "")
    if not m:
        return None
    sid = int(m.group(1))
    field = m.group(2).lower()
    value = m.group(3).strip()
    if field == "for_report":
        v = value.lower()
        if v in ("1","true","yes","y","on","enable","enabled"):
            value = 1
        elif v in ("0","false","no","n","off","disable","disabled"):
            value = 0
        else:
            try:
                value = 1 if int(value) != 0 else 0
            except Exception:
                return None
    return {"service_id": sid, field: value}
