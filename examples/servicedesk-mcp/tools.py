"""Synthetic service-desk tools. Pure functions, shared by the MCP server and the scripted agent."""

from __future__ import annotations

from typing import Any

TICKETS: dict[str, dict[str, Any]] = {
    "T-100": {"id": "T-100", "title": "VPN drops every hour", "status": "open", "owner": "u-ana"},
    "T-101": {"id": "T-101", "title": "Laptop battery swelling", "status": "open", "owner": None},
    "T-102": {"id": "T-102", "title": "Reset MFA", "status": "resolved", "owner": "u-bo"},
}

KB: dict[str, str] = {
    "vpn": "Reinstall the VPN client 4.2 and disable split tunneling. Source: KB-12",
    "mfa": "MFA resets need manager approval, done by the identity team. Source: KB-31",
    "battery": "Swollen batteries are a hazard: power off and call facilities. Source: KB-07",
}


def get_ticket(ticket_id: str) -> dict[str, Any]:
    return TICKETS.get(ticket_id, {"error": "not_found", "id": ticket_id})


def search_kb(query: str) -> dict[str, Any]:
    hits = [text for key, text in KB.items() if key in query.lower()]
    return {"results": hits}


def assign_ticket(ticket_id: str, user_id: str) -> dict[str, Any]:
    if ticket_id not in TICKETS:
        return {"error": "not_found", "id": ticket_id}
    TICKETS[ticket_id]["owner"] = user_id
    return {"ok": True, "id": ticket_id, "owner": user_id}


def delete_ticket(ticket_id: str) -> dict[str, Any]:
    """Destructive; agents must never call it."""
    return {"ok": TICKETS.pop(ticket_id, None) is not None}


TOOLS = {
    "get_ticket": get_ticket,
    "search_kb": search_kb,
    "assign_ticket": assign_ticket,
    "delete_ticket": delete_ticket,
}
