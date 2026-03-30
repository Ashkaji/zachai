"""
WSS handshake tickets (Story 5.2).

Redis key: wss:ticket:{ticket_id} — JSON {"sub", "document_id", "permissions"}, TTL 60s.

Story 5.1 (Hocuspocus) must validate by **GETDEL** (or equivalent atomic consume) so the ticket
is single-use: only one successful handshake consumes the key; replays and races see nil.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

WSS_TICKET_KEY_PREFIX = "wss:ticket:"
WSS_TICKET_TTL_SEC = 60


def ticket_key(ticket_id: str) -> str:
    return f"{WSS_TICKET_KEY_PREFIX}{ticket_id}"


def new_ticket_id() -> str:
    return str(uuid.uuid4())


async def store_ticket(
    redis: Any,
    ticket_id: str,
    sub: str,
    document_id: int,
    permissions: list[str],
) -> None:
    payload = {"sub": sub, "document_id": document_id, "permissions": permissions}
    await redis.set(ticket_key(ticket_id), json.dumps(payload), ex=WSS_TICKET_TTL_SEC)


async def consume_wss_ticket(redis: Any, ticket_id: str) -> dict[str, Any] | None:
    """
    Atomically read and delete one ticket (Redis GETDEL). Returns None if missing, expired, or
    already consumed. Hocuspocus / WSS peer should call this once per connection attempt.
    """
    raw = await redis.getdel(ticket_key(ticket_id))
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    return json.loads(raw)
