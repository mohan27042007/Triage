"""OpenAI-powered classification for the local-first Triage prototype."""

import json
import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = "gpt-5.6"

SYSTEM_PROMPT = """You are the classification engine for Triage, a student inbox assistant.

Classify the supplied text into exactly one category:
- Obligation: a notice requiring or strongly suggesting a student action, such as
  registration, form, attendance request, deadline, payment, poll, or mandatory event.
- Study Material: academic content intended to help learning or assessment
  preparation, such as notes, a syllabus excerpt, question bank, mock-paper question,
  or unit material.
- Noise: content that does not require action and is not useful study material, such
  as casual chat, promotions, greetings, duplicates, or irrelevant announcements.

Extract a deadline only when the text explicitly gives one. Preserve it as a concise
human-readable string instead of guessing a date. Set mandatory to true only for an
explicit requirement, false for an explicitly optional item, and null when the text
 does not say. Give a concise, evidence-based reason. Do not invent facts."""

CLASSIFICATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "category": {
            "type": "string",
            "enum": ["Obligation", "Study Material", "Noise"],
        },
        "reason": {"type": "string"},
        "deadline": {"type": ["string", "null"]},
        "mandatory": {"type": ["boolean", "null"]},
    },
    "required": ["category", "reason", "deadline", "mandatory"],
}


def classify(text: str) -> dict[str, Any]:
    """Classify one non-empty piece of student-facing text with GPT-5.6."""
    if not text or not text.strip():
        raise ValueError("Text cannot be empty.")

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. Add it to backend/.env."
        )

    client = OpenAI()
    response = client.responses.create(
        model=MODEL,
        instructions=SYSTEM_PROMPT,
        input=text.strip(),
        text={
            "format": {
                "type": "json_schema",
                "name": "triage_classification",
                "strict": True,
                "schema": CLASSIFICATION_SCHEMA,
            }
        },
    )

    try:
        result = json.loads(response.output_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "The model returned an invalid classification response."
        ) from exc

    return result
