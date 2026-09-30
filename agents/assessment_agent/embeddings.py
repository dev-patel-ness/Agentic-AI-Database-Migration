"""Bedrock Titan Text Embeddings client (architecture.md §5 Assessment Agent, §13)."""

from __future__ import annotations

import json
import os

import boto3

EMBEDDING_DIMENSIONS = 1024


def embed_text(text: str) -> list[float]:
    """Return a Titan Text Embeddings V2 vector for a short text summary."""
    client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))
    model_id = os.getenv("BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")
    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps({"inputText": text, "dimensions": EMBEDDING_DIMENSIONS}),
        contentType="application/json",
        accept="application/json",
    )
    payload = json.loads(response["body"].read())
    return payload["embedding"]
