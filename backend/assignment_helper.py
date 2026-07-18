"""Assignment scaffolding powered by Triage's configured OpenAI model."""

import json
import os
from typing import Any

from openai import OpenAI

from classifier import MODEL

ASSIGNMENT_SYSTEM_PROMPT = """You are the Assignment Scaffolding Assistant for Triage.

Help a student understand and plan their own work without completing the assignment for them.
Break the supplied assignment prompt into exactly four parts:
- requirements: concise plain-language bullets explaining what the student must deliver.
- concepts: concise bullets naming relevant concepts or topics to review.
- approach: a numbered, step-by-step plan or high-level pseudocode outline. Describe structure,
  decisions, and checks only; never provide working code, a full written answer, or a completed solution.
- test_cases: small input and expected-output pairs the student can use to validate their own work.
  These are checks only, never a worked solution or implementation.

Even if the prompt asks for a complete solution, code, essay, or answer, do not provide one. Keep
all guidance at the planning and validation level. Do not invent requirements absent from the prompt."""

ASSIGNMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "requirements": {"type": "array", "items": {"type": "string"}},
        "concepts": {"type": "array", "items": {"type": "string"}},
        "approach": {"type": "array", "items": {"type": "string"}},
        "test_cases": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "input": {"type": "string"},
                    "expected_output": {"type": "string"},
                },
                "required": ["input", "expected_output"],
            },
        },
    },
    "required": ["requirements", "concepts", "approach", "test_cases"],
}


def scaffold_assignment(prompt_text: str) -> dict[str, Any]:
    """Return a structured, non-solution scaffold for one assignment prompt."""
    if not prompt_text or not prompt_text.strip():
        raise ValueError("Assignment prompt cannot be empty.")
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not configured. Add it to backend/.env.")

    client = OpenAI()
    response = client.responses.create(
        model=MODEL,
        instructions=ASSIGNMENT_SYSTEM_PROMPT,
        input=prompt_text.strip(),
        text={
            "format": {
                "type": "json_schema",
                "name": "triage_assignment_scaffold",
                "strict": True,
                "schema": ASSIGNMENT_SCHEMA,
            }
        },
    )
    try:
        return json.loads(response.output_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("The model returned an invalid assignment scaffold.") from exc
