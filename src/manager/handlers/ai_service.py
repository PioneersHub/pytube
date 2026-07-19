"""
Multi-provider AI service for generating text descriptions.

Single source of truth: ALL AI configuration lives under one nested `ai_service:`
block in config.yaml / config_local.yaml:

    ai_service:
      provider: "anthropic"          # active provider (openai|anthropic|google|cohere)
      prompts:
        teaser: >
        description: >
        description_from_transcript: >
      openai:    { api_key, model, organization, temperature: {teaser, description} }
      anthropic: { api_key, model, max_tokens, temperature: {teaser, description} }
      google:    { api_key, model, safety_settings, temperature: {teaser, description} }
      cohere:    { api_key, model, temperature: {teaser, description} }

All readers go through the accessors below, so there is exactly one place that
resolves the active provider, its credentials, and the prompts. Missing config
fails fast (ValueError) — no silent fallbacks.
"""

import shutil
import subprocess
from abc import ABC, abstractmethod

from manager import conf, logger
from manager.utils.common import SafeConfig

# ---------------------------------------------------------------------------
# Single-point-of-truth config accessors
# ---------------------------------------------------------------------------


def active_provider_name() -> str:
    """Return the active provider name from `ai_service.provider` (fail-fast).

    `gemini` is accepted as an alias for `google`.
    """
    name = SafeConfig(conf).get("ai_service.provider")
    if not name:
        raise ValueError(
            "ai_service.provider not configured. Set `ai_service.provider` "
            "(openai|anthropic|google|cohere) in config_local.yaml."
        )
    name = str(name).lower()
    return "google" if name == "gemini" else name


def active_provider_config(name: str | None = None):
    """Return the sub-config for the active (or named) provider (fail-fast)."""
    name = name or active_provider_name()
    provider_config = SafeConfig(conf).get(f"ai_service.{name}")
    if not provider_config:
        raise ValueError(f"ai_service.{name} configuration not found in config.")
    return provider_config


def provider_prompt(key: str, default: str | None = None) -> str | None:
    """Return a generation prompt from `ai_service.prompts.<key>`."""
    return SafeConfig(conf).get(f"ai_service.prompts.{key}", default)


def provider_temperature(task: str, default: float) -> float:
    """Return the temperature for a task (`teaser`/`description`) of the active provider."""
    name = active_provider_name()
    return SafeConfig(conf).get(f"ai_service.{name}.temperature.{task}", default)


# ---------------------------------------------------------------------------
# Providers (each receives its own resolved sub-config)
# ---------------------------------------------------------------------------


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    @abstractmethod
    def generate_text(self, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float) -> str:
        """Generate text based on prompts."""


class OpenAIProvider(AIProvider):
    """OpenAI-compatible chat-completions provider.

    Serves the hosted OpenAI API and, via the optional `base_url` setting, any
    OpenAI-compatible endpoint — e.g. a local MLX server (see `MLXProvider`).
    """

    config_section = "openai"
    default_model = "gpt-4-turbo"

    def __init__(self, provider_config):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError("Please install openai: pip install openai") from exc

        api_key = provider_config.get("api_key")
        if not api_key:
            raise ValueError(f"api_key not found in ai_service.{self.config_section} configuration")
        model = provider_config.get("model", self.default_model)
        if not model:
            raise ValueError(f"model not configured in ai_service.{self.config_section}")
        self.client = OpenAI(
            api_key=api_key,
            organization=provider_config.get("organization"),
            base_url=provider_config.get("base_url") or None,
        )
        self.model = model

    def generate_text(self, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content


class AnthropicProvider(AIProvider):
    """Anthropic Claude provider."""

    def __init__(self, provider_config):
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise ImportError("Please install anthropic: pip install anthropic") from exc

        api_key = provider_config.get("api_key")
        if not api_key:
            raise ValueError("api_key not found in ai_service.anthropic configuration")
        self.client = Anthropic(api_key=api_key)
        self.model = provider_config.get("model", "claude-sonnet-5")
        self.max_tokens = provider_config.get("max_tokens", 1000)

    def generate_text(self, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float) -> str:
        message = self.client.messages.create(
            model=self.model,
            max_tokens=min(max_tokens, self.max_tokens),
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return message.content[0].text


class GoogleProvider(AIProvider):
    """Google Gemini provider."""

    def __init__(self, provider_config):
        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise ImportError("Please install google-generativeai: pip install google-generativeai") from exc

        api_key = provider_config.get("api_key")
        if not api_key:
            raise ValueError("api_key not found in ai_service.google configuration")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(provider_config.get("model", "gemini-pro"))
        self.safety_settings = provider_config.get("safety_settings", {})

    def generate_text(self, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float) -> str:
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        generation_config = {"temperature": temperature, "max_output_tokens": max_tokens}
        response = self.model.generate_content(
            full_prompt, generation_config=generation_config, safety_settings=self.safety_settings
        )
        return response.text


class CohereProvider(AIProvider):
    """Cohere provider."""

    def __init__(self, provider_config):
        try:
            import cohere
        except ImportError as exc:
            raise ImportError("Please install cohere: pip install cohere") from exc

        api_key = provider_config.get("api_key")
        if not api_key:
            raise ValueError("api_key not found in ai_service.cohere configuration")
        self.client = cohere.Client(api_key)
        self.model = provider_config.get("model", "command")

    def generate_text(self, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float) -> str:
        prompt = f"{system_prompt}\n\n{user_prompt}"
        response = self.client.generate(
            model=self.model,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.generations[0].text.strip()


class ClaudeCodeProvider(AIProvider):
    """Generate via the local Claude Code CLI in print mode.

    Uses the machine's Claude subscription instead of API credits. The CLI is an
    agentic tool, so it is pinned to a single turn with all tools disabled to make
    it behave as a plain text generator.

    Note: the CLI exposes neither `max_tokens` nor `temperature`; output length is
    governed by the prompt alone, and both arguments are accepted but ignored.
    """

    config_section = "claude_code"
    # Nothing may touch the machine while we only want text back.
    DISALLOWED_TOOLS = "Bash,Read,Write,Edit,NotebookEdit,WebFetch,WebSearch,Glob,Grep,Task,TodoWrite"

    def __init__(self, provider_config):
        self.binary = provider_config.get("binary", "claude")
        if not shutil.which(self.binary):
            raise ValueError(
                f"Claude Code CLI '{self.binary}' not found in PATH (ai_service.{self.config_section}.binary)"
            )
        self.model = provider_config.get("model", "sonnet")
        self.timeout = int(provider_config.get("timeout", 600))

    def generate_text(self, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float) -> str:  # noqa: ARG002
        cmd = [
            self.binary,
            "--print",
            "--system-prompt", system_prompt,
            "--output-format", "text",
            "--model", self.model,
            "--max-turns", "1",
            "--disallowed-tools", self.DISALLOWED_TOOLS,
            "--no-session-persistence",
        ]
        try:
            proc = subprocess.run(  # noqa: S603
                cmd, input=user_prompt, capture_output=True, text=True, timeout=self.timeout, check=False
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Claude Code CLI timed out after {self.timeout}s") from exc
        if proc.returncode != 0:
            raise RuntimeError(f"Claude Code CLI failed (exit {proc.returncode}): {proc.stderr.strip()[:300]}")
        text = proc.stdout.strip()
        if not text:
            raise RuntimeError("Claude Code CLI returned an empty response")
        return text


class MLXProvider(OpenAIProvider):
    """Local MLX model served over an OpenAI-compatible endpoint.

    Keeps generation on-device (no data leaves the machine). Requires `base_url`
    and `model` in `ai_service.mlx`; `api_key` is whatever the local server expects.
    """

    config_section = "mlx"
    default_model = ""  # no sensible default: the served model must be named explicitly


_PROVIDERS = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "google": GoogleProvider,
    "cohere": CohereProvider,
    "mlx": MLXProvider,
    "claude_code": ClaudeCodeProvider,
}


def get_ai_provider() -> AIProvider:
    """Instantiate the configured AI provider from the single `ai_service:` block."""
    name = active_provider_name()
    if name not in _PROVIDERS:
        raise ValueError(f"Unknown AI service: {name}. Options: {list(_PROVIDERS)}")
    provider_config = active_provider_config(name)
    try:
        return _PROVIDERS[name](provider_config)
    except Exception as e:
        logger.error(f"Failed to initialize {name} provider: {e}")
        raise


# ---------------------------------------------------------------------------
# Text-generation entry points
# ---------------------------------------------------------------------------


def teaser_text(text: str, max_tokens: int = 50, temperature: float | None = None) -> str:
    """Generate a teaser text using the configured AI provider."""
    provider = get_ai_provider()
    if temperature is None:
        temperature = provider_temperature("teaser", 0.7)
    system_prompt = provider_prompt("teaser", "Generate a teaser for the following text:")
    return provider.generate_text(
        system_prompt=system_prompt, user_prompt=text, max_tokens=max_tokens, temperature=temperature
    )


def sized_text(text: str, max_tokens: int = 100, temperature: float | None = None) -> str:
    """Generate a sized description text using the configured AI provider."""
    provider = get_ai_provider()
    if temperature is None:
        temperature = provider_temperature("description", 0.9)
    prompt_template = provider_prompt("description", "Generate a description with max {max_tokens} tokens:")
    system_prompt = prompt_template.format(max_tokens=max_tokens)
    return provider.generate_text(
        system_prompt=system_prompt, user_prompt=text, max_tokens=max_tokens, temperature=temperature
    )


def summary_from_transcript(
    transcript: str,
    grounding: str = "",
    max_tokens: int = 700,
    temperature: float | None = None,
    max_words: int | None = None,
) -> str:
    """Summarize a talk from its transcript using the configured AI provider.

    Used only when a transcript is available. Uses the
    `ai_service.prompts.description_from_transcript` system prompt for a neutral,
    technically precise summary. The transcript is truncated to `transcripts.max_chars`
    to bound context/cost. `grounding` (e.g. title/speakers) anchors the model.
    """
    provider = get_ai_provider()
    if temperature is None:
        temperature = provider_temperature("description", 0.9)
    prompt_template = provider_prompt(
        "description_from_transcript", "Summarize the following talk transcript in about {max_words} words:"
    )
    # Word count drives the prompt (token limits only cut the response off), so derive a
    # sensible default from max_tokens when the caller does not specify one.
    system_prompt = prompt_template.format(max_tokens=max_tokens, max_words=max_words or int(max_tokens / 2.8))

    max_chars = SafeConfig(conf).get("transcripts.max_chars", 48000)
    clipped = transcript[:max_chars] if max_chars else transcript
    user_prompt = f"{grounding}\n\nTranscript:\n{clipped}" if grounding else f"Transcript:\n{clipped}"

    return provider.generate_text(
        system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=max_tokens, temperature=temperature
    )
