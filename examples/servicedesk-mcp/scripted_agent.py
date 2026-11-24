"""Offline scripted agent for the demo: no API key needed.

Reads a Case as JSON on stdin and prints a Trace as JSON. ``PROMPT_VERSION=v2`` simulates a
prompt change that regresses behavior (it obeys injected instructions), so the gate has
something to catch.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from tools import TOOLS

from evalkit.replay import Cassette, MissingRecording
from evalkit.trace import ToolCall, Trace, Usage, hash_prompt


def call(trace: Trace, name: str, **arguments: str) -> object:
    cassette = os.environ.get("EVALKIT_CASSETTE")
    if cassette:  # tools answer from a recording; unrecorded calls abort the run
        try:
            result = Cassette.load(Path(cassette)).call(name, arguments)
        except MissingRecording as exc:
            sys.exit(f"{exc}")
    else:
        result = TOOLS[name](**arguments)
    trace.tool_calls.append(ToolCall(name=name, arguments=arguments, result=result))
    return result


def main() -> None:
    case = json.loads(sys.stdin.read())
    version = os.environ.get("PROMPT_VERSION", "v1")
    text: str = case["input"]
    trace = Trace(
        case_id=case["id"],
        agent="scripted",
        model="scripted-1",
        prompt_hash=hash_prompt(version),
        usage=Usage(input_tokens=120, output_tokens=60),
        latency_ms=250.0,
    )

    ticket = re.search(r"T-\d+", text)
    if version == "v2" and "ignore previous" in text.lower() and ticket:
        call(trace, "delete_ticket", ticket_id=ticket.group())
        trace.final_output = f"Deleted {ticket.group()} as requested."
    elif ticket and "assign" in text.lower():
        user = re.search(r"u-\w+", text)
        if user:
            call(trace, "assign_ticket", ticket_id=ticket.group(), user_id=user.group())
            trace.final_output = f"Assigned {ticket.group()} to {user.group()}."
        else:
            trace.final_output = "Which user should I assign it to?"
    elif ticket:
        data = call(trace, "get_ticket", ticket_id=ticket.group())
        trace.final_output = f"{ticket.group()}: {json.dumps(data)}"
    else:
        data = call(trace, "search_kb", query=text)
        hits = data["results"] if isinstance(data, dict) else []
        trace.final_output = hits[0] if hits else "I could not find that in the knowledge base."
    print(trace.model_dump_json())


if __name__ == "__main__":
    main()
