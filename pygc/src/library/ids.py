"""Replaceable asynchronous ID provider, with explicit entity namespaces."""

from typing import Literal
from uuid import uuid4


async def generate_id(kind: Literal["pull_request", "comment", "issue"]) -> str:
    """Generate a random ID; kind leaves room for a future coordinated provider."""
    return uuid4().hex
