from __future__ import annotations

from src.proxy.protocols.openai import extract_prompt, replace_prompt


class TestExtractPrompt:

    def test_single_user_message_string(self):
        body = {"messages": [{"role": "user", "content": "hello world"}]}
        assert extract_prompt(body) == "hello world"

    def test_system_message_included(self):
        """System messages are included — they may also contain proprietary code."""
        body = {"messages": [
            {"role": "system", "content": "you are helpful"},
            {"role": "user", "content": "what is 2+2"},
        ]}
        result = extract_prompt(body)
        assert "you are helpful" in result
        assert "what is 2+2" in result

    def test_multiple_user_messages_concatenated(self):
        body = {"messages": [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "second"},
        ]}
        assert "first" in extract_prompt(body)
        assert "second" in extract_prompt(body)

    def test_content_as_array_of_parts(self):
        body = {"messages": [{"role": "user", "content": [
            {"type": "text", "text": "explain pricing_spread"},
        ]}]}
        assert extract_prompt(body) == "explain pricing_spread"

    def test_content_array_skips_non_text_parts(self):
        body = {"messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "http://example.com/img.png"}},
            {"type": "text", "text": "what is in this image?"},
        ]}]}
        assert extract_prompt(body) == "what is in this image?"

    def test_empty_messages_returns_empty(self):
        assert extract_prompt({"messages": []}) == ""

    def test_missing_messages_returns_empty(self):
        assert extract_prompt({}) == ""

    def test_system_only_still_extracted(self):
        """A system-only message is still scanned — it may contain proprietary code."""
        body = {"messages": [{"role": "system", "content": "be helpful"}]}
        assert extract_prompt(body) == "be helpful"


class TestReplacePrompt:

    def test_replaces_last_user_message_string(self):
        body = {"messages": [{"role": "user", "content": "original"}]}
        result = replace_prompt(body, "replacement")
        assert result["messages"][0]["content"] == "replacement"  # type: ignore[index]

    def test_replaces_last_user_message_not_first(self):
        body = {"messages": [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "second"},
        ]}
        result = replace_prompt(body, "new")
        msgs = result["messages"]  # type: ignore[index]
        assert msgs[0]["content"] == "first"
        assert msgs[2]["content"] == "new"

    def test_does_not_mutate_original(self):
        body = {"messages": [{"role": "user", "content": "original"}]}
        replace_prompt(body, "new")
        assert body["messages"][0]["content"] == "original"  # type: ignore[index]

    def test_replaces_content_in_array_form(self):
        body = {"messages": [{"role": "user", "content": [
            {"type": "text", "text": "original text"},
        ]}]}
        result = replace_prompt(body, "replaced")
        content = result["messages"][0]["content"]  # type: ignore[index]
        assert content[0]["text"] == "replaced"  # type: ignore[index]
