from __future__ import annotations

# The OpenAI chat/completions format uses the same `messages` structure as
# Anthropic, so extract_prompt and replace_prompt are identical in logic.
# They are re-exported here so callers can import from the protocol module
# without depending on the Anthropic module directly.
from src.proxy.protocols.anthropic import extract_prompt, replace_prompt

__all__ = ["extract_prompt", "replace_prompt"]
