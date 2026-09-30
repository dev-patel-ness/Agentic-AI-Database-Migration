"""Bedrock Nova Pro client for the Planner Agent's LLM risk-refinement step
(architecture.md §5 Planner Agent, §13 Observability notes every Bedrock call)."""

from __future__ import annotations

import json
import os
from typing import Any

import boto3


def converse_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    """Invoke Nova Pro via the Converse API and parse the reply as JSON.

    Raises ValueError on any non-JSON reply -- callers treat that the same as
    any other Bedrock failure (fall back to the deterministic heuristic).
    """
    client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))
    model_id = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")
    response = client.converse(
        modelId=model_id,
        system=[{"text": system_prompt}],
        messages=[{"role": "user", "content": [{"text": user_prompt}]}],
        inferenceConfig={
            "maxTokens": int(os.getenv("BEDROCK_MAX_TOKENS", "4096")),
            "temperature": float(os.getenv("BEDROCK_TEMPERATURE", "0.7")),
        },
    )
    text = response["output"]["message"]["content"][0]["text"].strip()
    if text.startswith("```"):
        # Models occasionally wrap JSON in a fenced code block despite
        # instructions not to -- strip it defensively rather than fail.
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"model did not return valid JSON: {text!r}") from exc
