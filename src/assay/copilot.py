"""AI copilot for *authoring* checks -- never for judging data.

The single most important idea in this file: the AI's job ends at producing a
draft list of check specs. Every spec it returns is passed through
`build_check` (the deterministic registry). Anything the model invents that is
not a real, registered, deterministic check type -- or that has invalid
arguments -- is silently discarded. So:

  * the AI can suggest and explain,
  * but only auditable, deterministic checks ever run against your data,
  * and the model is never in the runtime pass/fail path.

The model is injected as a `Completer` (a plain callable), so this module is
fully testable with a fake model and provider-agnostic. `anthropic_completer`
is provided as one concrete implementation using the Anthropic API.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from collections.abc import Callable
from typing import Any

from .checks import available_checks, build_check
from .profile import DatasetProfile

# (system_prompt, user_prompt) -> raw model text
Completer = Callable[[str, str], str]


_SYSTEM = (
    "You are a data-quality assistant. You ONLY output data validation checks "
    "as JSON. You never explain, never add prose, never use markdown fences. "
    "Output must be a JSON array of check objects."
)


def _catalog() -> str:
    return (
        "Allowed check types and their fields:\n"
        "- columns_exist: {columns: [str]}\n"
        "- not_null: {column: str}\n"
        "- unique: {column: str}\n"
        "- in_set: {column: str, values: [any]}\n"
        "- in_range: {column: str, min?: number, max?: number}\n"
        "- matches_regex: {column: str, pattern: str}\n"
        "- row_count: {min?: int, max?: int}\n"
        "- no_duplicate_rows: {subset?: [str]}\n"
        "Every check may add \"severity\": \"error\" (default) or \"warn\".\n"
        f"Registered types: {', '.join(available_checks())}."
    )


def _extract_json_array(text: str) -> list[dict[str, Any]]:
    """Be forgiving about models that wrap JSON in prose or fences."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    return data if isinstance(data, list) else []


def _validate(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """THE TRUST GATE. Keep only specs that build into a real Check."""
    good: list[dict[str, Any]] = []
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        try:
            build_check(dict(spec))  # raises on unknown type / bad args
        except Exception:
            continue  # discard anything the model got wrong
        good.append(spec)
    return good


def checks_from_profile(
    profile: DatasetProfile,
    complete: Completer,
    suite_name: str = "ai_suggested_suite",
) -> dict[str, Any]:
    user = (
        _catalog()
        + "\n\nHere is a profile of the dataset. Propose a thorough but "
        "non-redundant check suite. Consider semantic types (email, uuid, "
        "categorical, etc.) and reasonable ranges.\n\n"
        + json.dumps(profile.to_dict(), indent=2)
    )
    raw = complete(_SYSTEM, user)
    checks = _validate(_extract_json_array(raw))
    return {"suite": suite_name, "checks": checks}


def checks_from_text(
    text: str,
    columns: list[str],
    complete: Completer,
    suite_name: str = "nl_suggested_suite",
) -> dict[str, Any]:
    user = (
        _catalog()
        + f"\n\nColumns available: {columns}\n\n"
        + "Convert this plain-English data-quality intent into checks:\n"
        + f'"""{text}"""'
    )
    raw = complete(_SYSTEM, user)
    checks = _validate(_extract_json_array(raw))
    return {"suite": suite_name, "checks": checks}


# --------------------------------------------------------------------------- #
# One concrete Completer using the Anthropic API (no SDK dependency).
# --------------------------------------------------------------------------- #


def anthropic_completer(
    model: str = "claude-sonnet-5",
    api_key: str | None = None,
    max_tokens: int = 1500,
) -> Completer:
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(
            "No API key. Set ANTHROPIC_API_KEY or pass api_key=..., "
            "or use the deterministic profiler (suggest_from_profile) instead."
        )

    def complete(system: str, user: str) -> str:
        body = json.dumps(
            {
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            }
        ).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={
                "content-type": "application/json",
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read())
        return "".join(
            block.get("text", "")
            for block in payload.get("content", [])
            if block.get("type") == "text"
        )

    return complete
