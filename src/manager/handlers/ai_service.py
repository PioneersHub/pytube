"""
Multi-provider AI service for generating text descriptions.

This module provides a unified interface for multiple AI providers:
- OpenAI (GPT-3.5, GPT-4)
- Anthropic (Claude)
- Google (Gemini)
- Cohere

Configuration in config.yaml/config_local.yaml:
    ai_service: "openai"  # Active service selection

    openai:
        api_key: "your-api-key"
        model: "gpt-3.5-turbo"
        temperature:
            teaser: 0.7
            description: 0.9
"""

from abc import ABC, abstractmethod

from manager import conf, logger
from manager.utils.common import SafeConfig


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    @abstractmethod
    def generate_text(self, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float) -> str:
        """Generate text based on prompts."""
        pass


class OpenAIProvider(AIProvider):
    """OpenAI GPT provider."""

    def __init__(self):
        try:
            from openai import OpenAI

            safe_conf = SafeConfig(conf)
            api_key = safe_conf.get("openai.api_key")
            if not api_key:
                raise ValueError("OpenAI API key not configured. Please set openai.api_key in config_local.yaml")

            organization = safe_conf.get("openai.organization")
            self.client = OpenAI(api_key=api_key, organization=organization)
            self.model = safe_conf.get("openai.model", "gpt-3.5-turbo")
        except ImportError:
            raise ImportError("Please install openai: pip install openai")

    def generate_text(self, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float) -> str:
        """Generate text using OpenAI."""
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

    def __init__(self):
        try:
            from anthropic import Anthropic

            safe_conf = SafeConfig(conf)
            api_key = safe_conf.get("anthropic.api_key")
            if not api_key:
                raise ValueError("Anthropic API key not configured. Please set anthropic.api_key in config_local.yaml")

            self.client = Anthropic(api_key=api_key)
            self.model = safe_conf.get("anthropic.model", "claude-3-sonnet-20240229")
            self.max_tokens = safe_conf.get("anthropic.max_tokens", 1000)
        except ImportError:
            raise ImportError("Please install anthropic: pip install anthropic")

    def generate_text(self, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float) -> str:
        """Generate text using Claude."""
        # Claude uses a different message format
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

    def __init__(self):
        try:
            import google.generativeai as genai

            safe_conf = SafeConfig(conf)
            api_key = safe_conf.get("google.api_key")
            if not api_key:
                raise ValueError("Google API key not configured. Please set google.api_key in config_local.yaml")

            genai.configure(api_key=api_key)
            model_name = safe_conf.get("google.model", "gemini-pro")
            self.model = genai.GenerativeModel(model_name)
            self.safety_settings = safe_conf.get("google.safety_settings", {})
        except ImportError:
            raise ImportError("Please install google-generativeai: pip install google-generativeai")

    def generate_text(self, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float) -> str:
        """Generate text using Gemini."""
        # Combine prompts for Gemini
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        generation_config = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }

        response = self.model.generate_content(
            full_prompt, generation_config=generation_config, safety_settings=self.safety_settings
        )
        return response.text


class CohereProvider(AIProvider):
    """Cohere provider."""

    def __init__(self):
        try:
            import cohere

            safe_conf = SafeConfig(conf)
            api_key = safe_conf.get("cohere.api_key")
            if not api_key:
                raise ValueError("Cohere API key not configured. Please set cohere.api_key in config_local.yaml")

            self.client = cohere.Client(api_key)
            self.model = safe_conf.get("cohere.model", "command")
        except ImportError:
            raise ImportError("Please install cohere: pip install cohere")

    def generate_text(self, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float) -> str:
        """Generate text using Cohere."""
        # Combine prompts for Cohere
        prompt = f"{system_prompt}\n\n{user_prompt}"

        response = self.client.generate(
            model=self.model,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.generations[0].text.strip()


# Factory function to get the appropriate provider
def get_ai_provider() -> AIProvider:
    """Get the configured AI provider."""
    safe_conf = SafeConfig(conf)
    service = safe_conf.get("ai_service", "openai").lower()

    providers = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "google": GoogleProvider,
        "gemini": GoogleProvider,  # Alias
        "cohere": CohereProvider,
    }

    if service not in providers:
        raise ValueError(f"Unknown AI service: {service}. Options: {list(providers.keys())}")

    try:
        return providers[service]()
    except Exception as e:
        logger.error(f"Failed to initialize {service} provider: {e}")
        raise


# Main functions that use the selected provider
def teaser_text(text: str, max_tokens: int = 50, temperature: float | None = None) -> str:
    """Generate a teaser text using the configured AI provider."""
    provider = get_ai_provider()
    safe_conf = SafeConfig(conf)
    service = safe_conf.get("ai_service", "openai").lower()

    # Use temperature from config if not specified
    if temperature is None:
        temperature = safe_conf.get(f"{service}.temperature.teaser", 0.7)

    system_prompt = safe_conf.get("prompts.teaser", "Generate a teaser for the following text:")

    return provider.generate_text(
        system_prompt=system_prompt, user_prompt=text, max_tokens=max_tokens, temperature=temperature
    )


def sized_text(text: str, max_tokens: int = 100, temperature: float | None = None) -> str:
    """Generate a sized description text using the configured AI provider."""
    provider = get_ai_provider()
    safe_conf = SafeConfig(conf)
    service = safe_conf.get("ai_service", "openai").lower()

    # Use temperature from config if not specified
    if temperature is None:
        temperature = safe_conf.get(f"{service}.temperature.description", 0.9)

    prompt_template = safe_conf.get("prompts.description", "Generate a description with max {max_tokens} tokens:")
    system_prompt = prompt_template.format(max_tokens=max_tokens)

    return provider.generate_text(
        system_prompt=system_prompt, user_prompt=text, max_tokens=max_tokens, temperature=temperature
    )
