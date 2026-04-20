"""Schema loader for the audit record schema."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"
AUDIT_RECORD_SCHEMA_PATH = SCHEMA_DIR / "audit_record.schema.json"


def load_audit_record_schema() -> dict[str, Any]:
    """Load the JSON-Schema for audit records from disk."""
    with AUDIT_RECORD_SCHEMA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)
