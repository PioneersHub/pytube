"""Tests for the single-source ai_service config accessors and fail-fast behavior."""

from unittest.mock import patch

import pytest
from omegaconf import OmegaConf

from manager.handlers import ai_service

ANTHROPIC_DESC_TEMP = 0.3


def _cfg(provider="anthropic", with_key=True, include_provider_key=True):
    d = {
        "ai_service": {
            "prompts": {
                "teaser": "teaser prompt",
                "description": "describe in {max_tokens}",
                "description_from_transcript": "summarize in {max_tokens}",
            },
            "anthropic": {
                "api_key": "k-ant" if with_key else "",
                "model": "claude-x",
                "max_tokens": 2000,
                "temperature": {"teaser": 0.5, "description": 0.3},
            },
            "openai": {
                "api_key": "k-oai",
                "model": "gpt-x",
                "temperature": {"teaser": 0.7, "description": 0.9},
            },
        },
        "transcripts": {"max_chars": 100},
    }
    if include_provider_key:
        d["ai_service"]["provider"] = provider
    return OmegaConf.create(d)


class TestAccessors:
    def test_active_provider_name(self):
        with patch.object(ai_service, "conf", _cfg("anthropic")):
            assert ai_service.active_provider_name() == "anthropic"

    def test_gemini_aliases_to_google(self):
        with patch.object(ai_service, "conf", _cfg("gemini")):
            assert ai_service.active_provider_name() == "google"

    def test_missing_provider_fails_fast(self):
        with (
            patch.object(ai_service, "conf", _cfg(include_provider_key=False)),
            pytest.raises(ValueError, match="ai_service.provider not configured"),
        ):
            ai_service.active_provider_name()

    def test_active_provider_config_returns_block(self):
        with patch.object(ai_service, "conf", _cfg("anthropic")):
            cfg = ai_service.active_provider_config()
            assert cfg.get("model") == "claude-x"

    def test_active_provider_config_missing_block_fails_fast(self):
        with (
            patch.object(ai_service, "conf", _cfg("cohere")),  # no cohere block present
            pytest.raises(ValueError, match="ai_service.cohere configuration not found"),
        ):
            ai_service.active_provider_config()

    def test_provider_prompt(self):
        with patch.object(ai_service, "conf", _cfg("anthropic")):
            assert ai_service.provider_prompt("description_from_transcript") == "summarize in {max_tokens}"

    def test_provider_temperature_scoped_to_active_provider(self):
        with patch.object(ai_service, "conf", _cfg("anthropic")):
            assert ai_service.provider_temperature("description", 0.9) == ANTHROPIC_DESC_TEMP


class TestGetProviderFailFast:
    def test_missing_api_key_fails_fast(self):
        # Use openai (installed in the test env); empty its api_key.
        cfg = _cfg("openai")
        cfg.ai_service.openai.api_key = ""
        with (
            patch.object(ai_service, "conf", cfg),
            pytest.raises(ValueError, match="api_key not found in ai_service.openai"),
        ):
            ai_service.get_ai_provider()
