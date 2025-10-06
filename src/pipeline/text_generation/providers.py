"""AI provider abstraction for multiple LLM providers."""

import json
import os
import re
from abc import ABC, abstractmethod

import structlog

logger = structlog.get_logger()


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    def __init__(self, config: dict):
        """Initialize provider with configuration.

        Args:
            config: Provider-specific configuration
        """
        self.config = config
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    @abstractmethod
    def generate(self, prompt: str) -> dict:
        """Generate response from prompt.

        Args:
            prompt: The formatted prompt

        Returns:
            Parsed JSON response
        """
        pass

    @abstractmethod
    def estimate_cost(self) -> dict:
        """Estimate API costs based on token usage.

        Returns:
            Cost estimation dictionary
        """
        pass

    def extract_json(self, response_text: str) -> dict:
        """Extract JSON from response text.

        Args:
            response_text: Raw response from AI

        Returns:
            Parsed JSON dictionary
        """
        # Find JSON in response (AI might add explanation text)
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.warning("failed_to_parse_json", error=str(e))
                # Try to clean common issues
                json_str = json_str.replace("\n", " ").replace("\\", "\\\\")
                try:
                    return json.loads(json_str)
                except:
                    pass

        # Fallback: return empty structure
        return {
            "short_description": response_text[:400] if response_text else "",
            "teaser": "",
            "tags": [],
            "key_takeaways": [],
            "target_audience": "all",
        }


class AnthropicProvider(AIProvider):
    """Anthropic Claude provider."""

    def __init__(self, config: dict):
        """Initialize Anthropic provider.

        Args:
            config: Provider configuration with model settings
        """
        super().__init__(config)

        # Get API key
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set. Please export ANTHROPIC_API_KEY=your_key")

        from anthropic import Anthropic

        self.client = Anthropic(api_key=api_key)

        # Get model from config, with fallback
        self.model = config.get("model", "claude-3-5-sonnet-20241022")
        self.max_tokens = config.get("max_tokens", 2000)
        self.temperature = config.get("temperature", 0.3)

    def generate(self, prompt: str) -> dict:
        """Generate response using Claude.

        Args:
            prompt: The formatted prompt

        Returns:
            Parsed JSON response
        """
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract text from response
            response_text = message.content[0].text

            # Track token usage
            if hasattr(message, "usage"):
                self.total_input_tokens += message.usage.input_tokens
                self.total_output_tokens += message.usage.output_tokens

            logger.info(
                "anthropic_generation_complete",
                model=self.model,
                input_tokens=getattr(message.usage, "input_tokens", 0),
                output_tokens=getattr(message.usage, "output_tokens", 0),
            )

            return self.extract_json(response_text)

        except Exception as e:
            logger.error("anthropic_api_error", error=str(e))
            raise

    def estimate_cost(self) -> dict:
        """Estimate Anthropic API costs.

        Returns:
            Cost estimation dictionary
        """
        # Anthropic pricing (as of late 2024)
        # Model-specific pricing
        pricing = {
            "claude-3-5-sonnet": {"input": 3.0, "output": 15.0},  # per million tokens
            "claude-3-opus": {"input": 15.0, "output": 75.0},
            "claude-3-haiku": {"input": 0.25, "output": 1.25},
        }

        # Determine which pricing to use
        model_base = self.model.rsplit("-", 1)[0]  # Remove date suffix
        rates = pricing.get(model_base, pricing["claude-3-5-sonnet"])

        input_cost = (self.total_input_tokens / 1_000_000) * rates["input"]
        output_cost = (self.total_output_tokens / 1_000_000) * rates["output"]
        total_cost = input_cost + output_cost

        return {
            "provider": "Anthropic",
            "model": self.model,
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "input_cost_usd": round(input_cost, 4),
            "output_cost_usd": round(output_cost, 4),
            "total_cost_usd": round(total_cost, 4),
        }


class OpenAIProvider(AIProvider):
    """OpenAI GPT provider."""

    def __init__(self, config: dict):
        """Initialize OpenAI provider.

        Args:
            config: Provider configuration with model settings
        """
        super().__init__(config)

        # Get API key
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set. Please export OPENAI_API_KEY=your_key")

        from openai import OpenAI

        self.client = OpenAI(api_key=api_key)

        # Get model from config, with fallback
        self.model = config.get("model", "gpt-4o-mini")
        self.max_tokens = config.get("max_tokens", 2000)
        self.temperature = config.get("temperature", 0.3)

    def generate(self, prompt: str) -> dict:
        """Generate response using OpenAI.

        Args:
            prompt: The formatted prompt

        Returns:
            Parsed JSON response
        """
        try:
            # Request JSON format explicitly
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that generates video metadata. Always respond with valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                response_format={"type": "json_object"},  # Force JSON response
            )

            # Extract text from response
            response_text = response.choices[0].message.content

            # Track token usage
            if response.usage:
                self.total_input_tokens += response.usage.prompt_tokens
                self.total_output_tokens += response.usage.completion_tokens

            logger.info(
                "openai_generation_complete",
                model=self.model,
                input_tokens=response.usage.prompt_tokens if response.usage else 0,
                output_tokens=response.usage.completion_tokens if response.usage else 0,
            )

            # Parse JSON directly (OpenAI returns valid JSON with response_format)
            try:
                return json.loads(response_text)
            except json.JSONDecodeError:
                return self.extract_json(response_text)

        except Exception as e:
            logger.error("openai_api_error", error=str(e))
            raise

    def estimate_cost(self) -> dict:
        """Estimate OpenAI API costs.

        Returns:
            Cost estimation dictionary
        """
        # OpenAI pricing (as of late 2024)
        pricing = {
            "gpt-4o": {"input": 2.50, "output": 10.00},  # per million tokens
            "gpt-4o-mini": {"input": 0.15, "output": 0.60},
            "gpt-4-turbo": {"input": 10.00, "output": 30.00},
            "gpt-4": {"input": 30.00, "output": 60.00},
            "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
        }

        # Find matching pricing
        rates = pricing.get(self.model, pricing["gpt-4o-mini"])

        input_cost = (self.total_input_tokens / 1_000_000) * rates["input"]
        output_cost = (self.total_output_tokens / 1_000_000) * rates["output"]
        total_cost = input_cost + output_cost

        return {
            "provider": "OpenAI",
            "model": self.model,
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "input_cost_usd": round(input_cost, 4),
            "output_cost_usd": round(output_cost, 4),
            "total_cost_usd": round(total_cost, 4),
        }


class ProviderFactory:
    """Factory for creating AI providers."""

    PROVIDERS = {
        "anthropic": AnthropicProvider,
        "openai": OpenAIProvider,
    }

    @classmethod
    def create(cls, provider_name: str, config: dict) -> AIProvider:
        """Create an AI provider instance.

        Args:
            provider_name: Name of the provider (anthropic, openai)
            config: Provider configuration

        Returns:
            AIProvider instance

        Raises:
            ValueError: If provider is not supported
        """
        provider_class = cls.PROVIDERS.get(provider_name.lower())
        if not provider_class:
            available = ", ".join(cls.PROVIDERS.keys())
            raise ValueError(f"Unsupported provider: {provider_name}. Available providers: {available}")

        logger.info("creating_ai_provider", provider=provider_name)
        return provider_class(config)
