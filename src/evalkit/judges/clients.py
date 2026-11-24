"""Judge backends.

- ``simulated``: deterministic heuristic stand-in for tests and offline demos. NOT an LLM.
- ``agent-sdk``: Claude via the Claude Agent SDK, using your local Claude Code login (no key).
- ``anthropic``: Claude through the Anthropic API (needs ``ANTHROPIC_API_KEY``).
"""

from __future__ import annotations

import json
import re

from evalkit.judges.llm import JudgeClient

_ANSWER = re.compile(r"<answer>\n(.*?)\n</answer>", re.DOTALL)
_EVIDENCE = re.compile(r"<tool_results>\n(.*?)\n</tool_results>", re.DOTALL)
_QUESTION = re.compile(r"<question>\n(.*?)\n</question>", re.DOTALL)
_CLAIM = re.compile(r"\b[A-Za-z]+-\w*\d\w*\b")
_REFUSAL = ("i cannot", "i can't", "i'm unable", "as an ai")


class SimulatedJudgeClient:
    """Fails an answer that is empty, refuses, or cites identifiers found nowhere in the
    question or tool results. Deterministic, so calibration tests are reproducible."""

    name = "simulated"

    async def complete(self, system: str, user: str) -> str:
        answer = (m.group(1) if (m := _ANSWER.search(user)) else "").strip()
        evidence = (m.group(1) if (m := _EVIDENCE.search(user)) else "").lower()
        question = (m.group(1) if (m := _QUESTION.search(user)) else "").lower()
        invented = sorted(
            {c for c in _CLAIM.findall(answer) if c.lower() not in evidence + question}
        )
        if not answer:
            verdict, why = "fail", "empty answer"
        elif any(r in answer.lower() for r in _REFUSAL):
            verdict, why = "fail", "refusal instead of an answer"
        elif invented:
            verdict, why = "fail", f"unsupported claims: {', '.join(invented)}"
        else:
            verdict, why = "pass", "no problems found"
        return json.dumps({"verdict": verdict, "reasoning": why})


class AgentSDKClient:
    """Uses ``claude-agent-sdk``; authentication comes from the local Claude Code login."""

    name = "agent-sdk"

    def __init__(self, model: str | None = None) -> None:
        self.model = model

    async def complete(self, system: str, user: str) -> str:
        try:
            from claude_agent_sdk import (
                AssistantMessage,
                ClaudeAgentOptions,
                ResultMessage,
                TextBlock,
                query,
            )
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("install the extra: pip install 'agent-evalkit[agent-sdk]'") from exc

        options = ClaudeAgentOptions(
            system_prompt=system,
            tools=[],  # a judge needs no tools
            max_turns=1,
            model=self.model,
            setting_sources=[],  # ignore the project's CLAUDE.md, hooks and skills
        )
        text, result = [], ""
        async for msg in query(prompt=user, options=options):
            if isinstance(msg, AssistantMessage):
                text += [b.text for b in msg.content if isinstance(b, TextBlock)]
            elif isinstance(msg, ResultMessage):
                if msg.is_error:
                    raise RuntimeError(f"agent-sdk judge failed: {msg.errors or msg.subtype}")
                result = msg.result or ""
        return result or "".join(text)


class AnthropicClient:
    name = "anthropic"

    def __init__(self, model: str, max_tokens: int = 512) -> None:
        self.model = model
        self.max_tokens = max_tokens

    async def complete(self, system: str, user: str) -> str:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("install the extra: pip install 'agent-evalkit[llm]'") from exc

        client = anthropic.AsyncAnthropic()
        resp = await client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in resp.content if b.type == "text")


def make_client(backend: str, model: str | None = None) -> JudgeClient:
    if backend == "simulated":
        return SimulatedJudgeClient()
    if backend == "agent-sdk":
        return AgentSDKClient(model)
    if backend == "anthropic":
        if not model:
            raise ValueError("--judge-model is required for the anthropic backend")
        return AnthropicClient(model)
    raise ValueError(f"unknown judge backend {backend!r}")
