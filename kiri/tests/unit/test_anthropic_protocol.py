from __future__ import annotations

# --- string content -----------------------------------------------------------


def test_extract_prompt_string_content() -> None:
    from src.proxy.protocols.anthropic import extract_prompt

    body = {"messages": [{"role": "user", "content": "hello world"}]}

    assert extract_prompt(body) == "hello world"


def test_extract_prompt_multiple_messages_string() -> None:
    from src.proxy.protocols.anthropic import extract_prompt

    body = {
        "messages": [
            {"role": "user", "content": "first message"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "second message"},
        ]
    }

    result = extract_prompt(body)

    assert "first message" in result
    assert "second message" in result


# --- block-list content -------------------------------------------------------


def test_extract_prompt_block_list_content() -> None:
    from src.proxy.protocols.anthropic import extract_prompt

    body = {
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": "hello blocks"}],
            }
        ]
    }

    assert extract_prompt(body) == "hello blocks"


def test_extract_prompt_multiple_text_blocks() -> None:
    from src.proxy.protocols.anthropic import extract_prompt

    body = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "part one"},
                    {"type": "text", "text": "part two"},
                ],
            }
        ]
    }

    result = extract_prompt(body)

    assert "part one" in result
    assert "part two" in result


def test_extract_prompt_skips_non_text_blocks() -> None:
    from src.proxy.protocols.anthropic import extract_prompt

    body = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "data": "..."}},
                    {"type": "text", "text": "describe this"},
                ],
            }
        ]
    }

    result = extract_prompt(body)

    assert "describe this" in result
    assert "base64" not in result


# --- edge cases ---------------------------------------------------------------


def test_extract_prompt_empty_messages_returns_empty() -> None:
    from src.proxy.protocols.anthropic import extract_prompt

    body: dict[str, object] = {"messages": []}

    assert extract_prompt(body) == ""


def test_extract_prompt_missing_messages_returns_empty() -> None:
    from src.proxy.protocols.anthropic import extract_prompt

    body: dict[str, object] = {"model": "claude-3-opus"}

    assert extract_prompt(body) == ""


def test_extract_prompt_returns_string() -> None:
    from src.proxy.protocols.anthropic import extract_prompt

    body = {"messages": [{"role": "user", "content": "test"}]}

    assert isinstance(extract_prompt(body), str)


# --- filter bypass via non-text content types --------------------------------
# A user could send source code inside tool_result / custom blocks to bypass
# L1/L2/L3 — the extractor must pull text from ANY block that carries it.


def test_extract_prompt_custom_type_with_text_field_is_extracted() -> None:
    """Block with unknown type but a 'text' field must still be extracted."""
    from src.proxy.protocols.anthropic import extract_prompt

    body = {
        "messages": [
            {
                "role": "user",
                "content": [{"type": "custom_type", "text": "proprietary_code_here"}],
            }
        ]
    }

    assert "proprietary_code_here" in extract_prompt(body)


def test_extract_prompt_tool_result_string_content_is_extracted() -> None:
    """tool_result with a plain string content must be extracted."""
    from src.proxy.protocols.anthropic import extract_prompt

    body = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_x",
                        "content": "secret_result_text",
                    }
                ],
            }
        ]
    }

    assert "secret_result_text" in extract_prompt(body)


def test_extract_prompt_tool_result_nested_blocks_extracted() -> None:
    """tool_result with nested text blocks must be extracted."""
    from src.proxy.protocols.anthropic import extract_prompt

    body = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_x",
                        "content": [{"type": "text", "text": "nested_source_code"}],
                    }
                ],
            }
        ]
    }

    assert "nested_source_code" in extract_prompt(body)


def test_extract_prompt_image_block_data_not_extracted() -> None:
    """Image blocks must NOT leak their binary data into the extracted prompt."""
    from src.proxy.protocols.anthropic import extract_prompt

    body = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "data": "abc123=="}},
                    {"type": "text", "text": "describe this image"},
                ],
            }
        ]
    }

    result = extract_prompt(body)

    assert "describe this image" in result
    assert "abc123" not in result  # binary image data must not leak


# --- redact_body -------------------------------------------------------------


def _upper(text: str) -> str:
    return text.upper()


def test_redact_body_plain_string_content() -> None:
    from src.proxy.protocols.anthropic import redact_body

    body = {"messages": [{"role": "user", "content": "hello"}]}
    result = redact_body(body, _upper)
    assert result["messages"][0]["content"] == "HELLO"  # type: ignore[index]


def test_redact_body_text_block() -> None:
    from src.proxy.protocols.anthropic import redact_body

    body = {"messages": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]}
    result = redact_body(body, _upper)
    assert result["messages"][0]["content"][0]["text"] == "HELLO"  # type: ignore[index]


def test_redact_body_tool_result_nested_block() -> None:
    """File content inside a tool_result nested text block must be redacted."""
    from src.proxy.protocols.anthropic import redact_body

    body = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_x",
                        "content": [{"type": "text", "text": "secret_code"}],
                    }
                ],
            }
        ]
    }
    result = redact_body(body, _upper)
    inner = result["messages"][0]["content"][0]["content"][0]  # type: ignore[index]
    assert inner["text"] == "SECRET_CODE"


def test_redact_body_tool_result_string_content() -> None:
    """File content as a plain string inside tool_result must be redacted."""
    from src.proxy.protocols.anthropic import redact_body

    body = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_x",
                        "content": "secret_code",
                    }
                ],
            }
        ]
    }
    result = redact_body(body, _upper)
    assert result["messages"][0]["content"][0]["content"] == "SECRET_CODE"  # type: ignore[index]


def test_redact_body_does_not_mutate_original() -> None:
    from src.proxy.protocols.anthropic import redact_body

    body = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "content": [{"type": "text", "text": "original"}],
                    }
                ],
            }
        ]
    }
    redact_body(body, _upper)
    inner = body["messages"][0]["content"][0]["content"][0]  # type: ignore[index]
    assert inner["text"] == "original"


def test_redact_body_skips_assistant_messages() -> None:
    from src.proxy.protocols.anthropic import redact_body

    body = {
        "messages": [
            {"role": "assistant", "content": "assistant text"},
            {"role": "user", "content": "user text"},
        ]
    }
    result = redact_body(body, _upper)
    assert result["messages"][0]["content"] == "assistant text"
    assert result["messages"][1]["content"] == "USER TEXT"  # type: ignore[index]
