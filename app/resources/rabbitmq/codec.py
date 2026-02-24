from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def encode_json_message(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def decode_json_message(body: bytes) -> dict[str, Any]:
    raw = body.decode("utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("RabbitMQ message body must be a JSON object.")
    return data


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_easy_contract_request(payload: dict[str, Any]) -> dict[str, Any]:
    return payload


def parse_checklist_request(payload: dict[str, Any]) -> dict[str, Any]:
    return payload


def parse_easy_contract_cancel(payload: dict[str, Any]) -> dict[str, Any]:
    return payload


def build_result_payload(
    *,
    job_id: str,
    result_type: str,
    status: str,
    data: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "type": result_type,
        "status": status,
        "data": data,
        "error": error,
        "processed_at": now_utc_iso(),
    }
