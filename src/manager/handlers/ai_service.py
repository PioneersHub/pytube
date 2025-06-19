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

            self.client = OpenAI(api_key=conf.openai.api_key, organization=conf.openai.get("organization"))
            self.model = conf.openai.get("model", "gpt-3.5-turbo")
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

            self.client = Anthropic(api_key=conf.anthropic.api_key)
            self.model = conf.anthropic.get("model", "claude-3-sonnet-20240229")
            self.max_tokens = conf.anthropic.get("max_tokens", 1000)
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

            genai.configure(api_key=conf.google.api_key)
            self.model = genai.GenerativeModel(conf.google.get("model", "gemini-pro"))
            self.safety_settings = conf.google.get("safety_settings", {})
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

            self.client = cohere.Client(conf.cohere.api_key)
            self.model = conf.cohere.get("model", "command")
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
    service = conf.get("ai_service", "openai").lower()

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
    service = conf.get("ai_service", "openai").lower()

    # Use temperature from config if not specified
    if temperature is None:
        service_config = getattr(conf, service, {})
        temperature = service_config.get("temperature", {}).get("teaser", 0.7)

    return provider.generate_text(
        system_prompt=conf.prompts.teaser, user_prompt=text, max_tokens=max_tokens, temperature=temperature
    )


def sized_text(text: str, max_tokens: int = 100, temperature: float | None = None) -> str:
    """Generate a sized description text using the configured AI provider."""
    provider = get_ai_provider()
    service = conf.get("ai_service", "openai").lower()

    # Use temperature from config if not specified
    if temperature is None:
        service_config = getattr(conf, service, {})
        temperature = service_config.get("temperature", {}).get("description", 0.9)

    system_prompt = conf.prompts.description.format(max_tokens=max_tokens)

    return provider.generate_text(
        system_prompt=system_prompt, user_prompt=text, max_tokens=max_tokens, temperature=temperature
    )
