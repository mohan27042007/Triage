"""OpenAI-powered classification for the local-first Triage prototype using GPT-5.6-luna."""

import json
import os
import re
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = "gpt-5.6-luna"

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
does not say. Set is_poll_or_form to true only for an Obligation that asks the student
to reply to a completion poll (for example, "reply YES if done") or complete a simple
form with named fields (for example, "fill in name and roll number"). Otherwise set it
to false. Give a concise, evidence-based reason. Do not invent facts."""

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
        "is_poll_or_form": {"type": "boolean", "default": False},
    },
    "required": ["category", "reason", "deadline", "mandatory"],
}

STUDY_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "topic": {"type": "string"},
                    "weight": {"type": "integer", "minimum": 1, "maximum": 10},
                    "subtopics": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["topic", "weight", "subtopics"],
            },
        }
    },
    "required": ["topics"],
}

STUDY_PLAN_PROMPT = """You are the study-planning engine for Triage, a student assistant.

Compare the supplied question bank with the supplied unit notes. Identify the most important
recurring or emphasized topics that a student should study. Return no more than eight topics,
ordered from highest to lowest priority. For each topic, assign a weight from 1 to 10 based on
how often it appears in the question bank and how strongly the unit notes emphasize it. Provide
3 to 6 concise subtopics or outline subtitles to study.

Do not write answers to questions, essay paragraphs, or solutions. Return study structure only.
Do not invent topics that are unsupported by the supplied material."""


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


def draft_poll_or_form_response(text: str) -> str | None:
    """Create a conservative, copy-only response draft from explicit message wording."""
    normalized = " ".join(text.split())
    completion_reply = re.search(r"\breply\s+(yes|no|done|completed)\b", normalized, re.IGNORECASE)
    if completion_reply:
        response = completion_reply.group(1).upper()
        return f"Suggested reply: {response}, completed"

    field_labels: list[str] = []
    for label, pattern in (
        ("Name", r"\b(?:full\s+)?name\b"),
        ("Roll number", r"\broll\s*(?:number|no\.?|#)?\b"),
        ("Email", r"\b(?:email|e-mail)\b"),
        ("Phone number", r"\b(?:phone|mobile)(?:\s+number)?\b"),
    ):
        if re.search(pattern, normalized, re.IGNORECASE):
            field_labels.append(label)
    if field_labels:
        return "Suggested form response:\n" + "\n".join(
            f"{label}: [enter your {label.lower()}]" for label in field_labels
        )
    return None


def build_study_plan(question_bank: str, unit_notes: str) -> list[dict[str, Any]]:
    """Create a ranked topic outline from a question bank and supporting unit notes."""
    if not question_bank.strip() or not unit_notes.strip():
        raise ValueError("Both question bank and unit notes must contain text.")
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not configured. Add it to backend/.env.")

    client = OpenAI()
    response = client.responses.create(
        model=MODEL,
        instructions=STUDY_PLAN_PROMPT,
        input=(
            "QUESTION BANK:\n"
            f"{question_bank.strip()}\n\n"
            "UNIT NOTES:\n"
            f"{unit_notes.strip()}"
        ),
        text={
            "format": {
                "type": "json_schema",
                "name": "triage_study_plan",
                "strict": True,
                "schema": STUDY_PLAN_SCHEMA,
            }
        },
    )
    try:
        result = json.loads(response.output_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("The model returned an invalid study plan response.") from exc

    return result["topics"]
