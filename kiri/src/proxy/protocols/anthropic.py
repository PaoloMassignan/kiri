from __future__ import annotations

from collections.abc import Callable


def extract_prompt(body: dict[str, object]) -> str:
    """Concatenate all text content from the messages list.

    Handles both string content and list-of-block content.  Text is extracted
    from ALL block types that carry a 'text' field or a nested 'content' array
    (e.g. tool_result), not only from blocks with type=='text'.  This prevents
    bypassing the filter by encoding source code in non-text content types.
    """
    messages = body.get("messages")
    if not isinstance(messages, list):
        return ""

    parts: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    parts.extend(_extract_text_from_block(block))

    return "\n".join(parts)


def _extract_text_from_block(block: dict[str, object]) -> list[str]:
    """Recursively extract all text strings from a content block.

    Handles:
    - {"type": "text", "text": "..."}          — standard text block
    - {"type": "custom", "text": "..."}        — any block with a direct text field
    - {"type": "tool_result", "content": "..."} — string content
    - {"type": "tool_result", "content": [...]} — nested block array (one level)

    Image blocks (no 'text' field, binary data in 'source') are ignored.
    """
    texts: list[str] = []

    # Direct 'text' field on the block itself
    text = block.get("text")
    if isinstance(text, str):
        texts.append(text)

    # Nested 'content' field (tool_result and similar)
    content = block.get("content")
    if isinstance(content, str):
        texts.append(content)
    elif isinstance(content, list):
        for inner in content:
            if isinstance(inner, dict):
                texts.extend(_extract_text_from_block(inner))

    return texts


def replace_prompt(body: dict[str, object], new_text: str) -> dict[str, object]:
    """Return a copy of *body* with the last user message content replaced.

    Only the modified message (and its parent list) are copied — unrelated
    parts of the body are shared by reference with the original.
    """
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        return body

    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue

        content = msg.get("content")
        if isinstance(content, str):
            updated_msg = {**msg, "content": new_text}
        elif isinstance(content, list):
            updated_blocks = list(content)
            for j, block in enumerate(updated_blocks):
                if isinstance(block, dict) and block.get("type") == "text":
                    updated_blocks[j] = {**block, "text": new_text}
                    break
            updated_msg = {**msg, "content": updated_blocks}
        else:
            return body

        updated_messages = list(messages)
        updated_messages[i] = updated_msg
        return {**body, "messages": updated_messages}

    return body


def redact_body(
    body: dict[str, object],
    redact_fn: Callable[[str], str],
) -> dict[str, object]:
    """Apply *redact_fn* to every text string in every user-role message.

    Unlike replace_prompt, recurses into nested content (tool_result blocks
    included) so that file content returned by Read tools is also redacted
    before being forwarded to the upstream LLM.
    """
    messages = body.get("messages")
    if not isinstance(messages, list):
        return body

    new_messages = list(messages)
    changed = False
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        new_content = _redact_content(msg.get("content"), redact_fn)
        if new_content is not msg.get("content"):
            new_messages[i] = {**msg, "content": new_content}
            changed = True

    return {**body, "messages": new_messages} if changed else body


def _redact_content(
    content: object,
    redact_fn: Callable[[str], str],
) -> object:
    if isinstance(content, str):
        redacted = redact_fn(content)
        return redacted if redacted != content else content
    if isinstance(content, list):
        new_list = list(content)
        changed = False
        for j, block in enumerate(new_list):
            if isinstance(block, dict):
                new_block = _redact_block(block, redact_fn)
                if new_block is not block:
                    new_list[j] = new_block
                    changed = True
        return new_list if changed else content
    return content


def _redact_block(
    block: dict[str, object],
    redact_fn: Callable[[str], str],
) -> dict[str, object]:
    updates: dict[str, object] = {}
    text = block.get("text")
    if isinstance(text, str):
        new_text = redact_fn(text)
        if new_text != text:
            updates["text"] = new_text
    if "content" in block:
        new_content = _redact_content(block["content"], redact_fn)
        if new_content is not block["content"]:
            updates["content"] = new_content
    return {**block, **updates} if updates else block
