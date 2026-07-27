"""Deterministic, explainable review routing for classified Triage items."""

from __future__ import annotations

import re
from typing import Any


_REQUIRED_LANGUAGE = re.compile(r"\b(required|mandatory|must)\b", re.IGNORECASE)
_OPTIONAL_LANGUAGE = re.compile(r"\b(optional|not required|not mandatory)\b", re.IGNORECASE)
_EXTERNAL_ACTION_LANGUAGE = re.compile(r"\b(reply|send|submit|pay|vote|register|sign)\b", re.IGNORECASE)


def route_policy(text: str, classification: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic review flags; no model confidence is used as a safety gate."""
    category = classification.get("category")
    is_obligation = category == "Obligation"
    reasons: list[str] = []
    if is_obligation and not classification.get("deadline"):
        reasons.append("obligation_missing_deadline")
    if _REQUIRED_LANGUAGE.search(text) and _OPTIONAL_LANGUAGE.search(text):
        reasons.append("conflicting_requirement_language")
    if is_obligation and (
        bool(classification.get("is_poll_or_form")) or _EXTERNAL_ACTION_LANGUAGE.search(text)
    ):
        reasons.append("external_action_requires_human_review")
    return {
        "review_required": bool(reasons),
        "review_reasons": reasons,
        "draft_eligible": bool(is_obligation and classification.get("is_poll_or_form")),
    }
