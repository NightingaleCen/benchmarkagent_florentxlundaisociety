import os

import pytest

from benchmarkrun.model_clients import (
    AnthropicModelClient,
    OpenAIModelClient,
    build_model_client,
    parse_model_spec,
)


# Anthropic's SDK requires a key at construction time; give it a fake one
# so we can instantiate clients in tests without hitting the network.
@pytest.fixture(autouse=True)
def _fake_keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def test_parse_model_spec_no_colon():
    assert parse_model_spec("claude-sonnet-4-6") == (None, "claude-sonnet-4-6")


def test_parse_model_spec_with_provider():
    assert parse_model_spec("anthropic:custom-llama") == (
        "anthropic",
        "custom-llama",
    )
    assert parse_model_spec("openai:my-gpt") == ("openai", "my-gpt")


def test_parse_model_spec_case_insensitive_provider():
    assert parse_model_spec("Anthropic:foo") == ("anthropic", "foo")


def test_parse_model_spec_unknown_provider():
    with pytest.raises(ValueError, match="unknown provider"):
        parse_model_spec("mistral:foo")


def test_parse_model_spec_empty_model_name():
    with pytest.raises(ValueError, match="empty model name"):
        parse_model_spec("anthropic:")


def test_prefix_detection_anthropic():
    c = build_model_client("claude-sonnet-4-6")
    assert isinstance(c, AnthropicModelClient)
    assert c.model_id == "claude-sonnet-4-6"


def test_prefix_detection_openai_gpt():
    c = build_model_client("gpt-4o-mini")
    assert isinstance(c, OpenAIModelClient)


def test_prefix_detection_openai_o_series():
    for m in ["o1-mini", "o3", "o4-mini"]:
        c = build_model_client(m)
        assert isinstance(c, OpenAIModelClient)


def test_spec_syntax_overrides_prefix_detection():
    """`openai:claude-something` forces OpenAI even though name looks like Claude."""
    c = build_model_client("openai:claude-lookalike")
    assert isinstance(c, OpenAIModelClient)
    assert c.model_id == "claude-lookalike"


def test_explicit_provider_kwarg_wins():
    c = build_model_client("my-custom", provider="anthropic")
    assert isinstance(c, AnthropicModelClient)
    assert c.model_id == "my-custom"


def test_explicit_provider_overrides_spec_syntax():
    c = build_model_client("openai:weird", provider="anthropic")
    assert isinstance(c, AnthropicModelClient)
    # model name from spec is preserved
    assert c.model_id == "weird"


def test_custom_name_without_provider_raises():
    with pytest.raises(ValueError, match="cannot determine provider"):
        build_model_client("my-custom-llama")


def test_error_message_suggests_fix():
    """The error for an undetectable name should teach the user how to disambiguate."""
    with pytest.raises(ValueError) as exc:
        build_model_client("weirdname")
    msg = str(exc.value)
    assert "anthropic:weirdname" in msg
    assert "openai:weirdname" in msg
    assert "--provider" in msg


def test_unknown_provider_override_raises():
    with pytest.raises(ValueError, match="unknown provider override"):
        build_model_client("anything", provider="mistral")
