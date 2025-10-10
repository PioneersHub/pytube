"""AI provider abstraction for multiple LLM providers."""

import json
import re
from abc import ABC, abstractmethod

import anthropic
import openai
import structlog
from anthropic import Anthropic
from openai import OpenAI
from pydantic import ValidationError

from .models import AIGeneratedResponse

logger = structlog.get_logger()


# Exception hierarchy for AI provider errors
class AIProviderError(Exception):
    """Base exception for AI provider errors."""

    pass


class AIRateLimitError(AIProviderError):
    """Rate limit exceeded - retryable."""

    pass


class AITimeoutError(AIProviderError):
    """Request timeout - retryable."""

    pass


class AIValidationError(AIProviderError):
    """Response validation failed - not retryable."""

    pass


class AIQuotaError(AIProviderError):
    """API quota exceeded - not retryable."""

    pass


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    # Required output schema
    REQUIRED_FIELDS = {
        "short_description": str,
        "teaser": str,
        "tags": list,
        "key_takeaways": list,
        "target_audience": str,
    }

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
            Parsed JSON response matching REQUIRED_FIELDS schema
        """
        pass

    @abstractmethod
    def estimate_cost(self) -> dict:
        """Estimate API costs based on token usage.

        Returns:
            Cost estimation dictionary
        """
        pass

    def set_constraints(self, constraints: dict) -> None:
        """Set constraints for response validation.

        Args:
            constraints: Constraints dictionary from config
        """
        self._constraints = constraints

    def validate_response(self, response: dict) -> dict:
        """Validate AI response strictly against schema and constraints.

        Args:
            response: Raw response dictionary

        Returns:
            Validated response dictionary

        Raises:
            AIValidationError: If response doesn't match schema or violates constraints
        """
        try:
            # Step 1: Validate schema with Pydantic
            try:
                validated_response = AIGeneratedResponse(**response)
            except ValidationError as e:
                logger.error(
                    "response_schema_invalid",
                    error=str(e),
                    response_keys=list(response.keys()),
                    missing_fields=[err["loc"][0] for err in e.errors() if err["type"] == "missing"],
                )
                raise AIValidationError(f"AI response schema validation failed: {e}") from e

            # Step 2: Validate constraints from config (if available)
            if hasattr(self, "_constraints"):
                self._validate_constraints(validated_response)

            # Convert back to dict
            result = validated_response.model_dump()

            logger.info(
                "response_validated",
                teaser_len=len(result.get("teaser_text", "")),
                short_words=len(result.get("short_text", "").split()),
                long_words=len(result.get("long_text", "").split()),
                tags_count=len(result.get("tags", [])),
                quotes_count=len(result.get("quotes", [])),
            )
            return result

        except AIValidationError:
            raise  # Re-raise our custom exception
        except Exception as e:
            error_msg = f"Unexpected validation error: {e}"
            logger.error("validation_unexpected_error", error=str(e))
            raise AIValidationError(error_msg) from e

    def _validate_constraints(self, response) -> None:
        """Validate response against configured constraints.

        Args:
            response: Validated AIGeneratedResponse object

        Raises:
            AIValidationError: If constraints are violated
        """
        constraints = self._constraints
        errors = []

        # Check teaser length
        teaser_max = constraints.get("teaser_text", {}).get("max_chars")
        if teaser_max and len(response.teaser_text) > teaser_max:
            errors.append(f"teaser_text: {len(response.teaser_text)} chars (max: {teaser_max})")

        # Check short text word count
        short_words = len(response.short_text.split())
        short_min = constraints.get("short_text", {}).get("min_words", 0)
        short_max = constraints.get("short_text", {}).get("max_words", 999999)
        if not (short_min <= short_words <= short_max):
            errors.append(f"short_text: {short_words} words (expected: {short_min}-{short_max})")

        # Check long text word count
        long_words = len(response.long_text.split())
        long_min = constraints.get("long_text", {}).get("min_words", 0)
        long_max = constraints.get("long_text", {}).get("max_words", 999999)
        if not (long_min <= long_words <= long_max):
            errors.append(f"long_text: {long_words} words (expected: {long_min}-{long_max})")

        # Check social text length
        social_max = constraints.get("social_text", {}).get("max_chars")
        if social_max and len(response.social_text) > social_max:
            errors.append(f"social_text: {len(response.social_text)} chars (max: {social_max})")

        # Check tags count
        tags_min = constraints.get("tags", {}).get("min_count", 0)
        tags_max = constraints.get("tags", {}).get("max_count", 999)
        tags_count = len(response.tags)
        if not (tags_min <= tags_count <= tags_max):
            errors.append(f"tags: {tags_count} items (expected: {tags_min}-{tags_max})")

        # Check quotes count
        quotes_expected = constraints.get("quotes", {}).get("count")
        quotes_count = len(response.quotes)
        if quotes_expected and quotes_count != quotes_expected:
            errors.append(f"quotes: {quotes_count} items (expected: {quotes_expected})")

        if errors:
            error_msg = "AI response violates constraints: " + "; ".join(errors)
            logger.error("constraint_violations", violations=errors)
            raise AIValidationError(error_msg)

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
                except json.JSONDecodeError:
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

        # Get API key from config
        api_key = config.get("api_key")
        if not api_key:
            raise ValueError("api_key not found in ai_service.anthropic configuration")

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

        Raises:
            AIRateLimitError: If rate limit exceeded
            AITimeoutError: If request times out
            AIQuotaError: If API quota exceeded
            AIProviderError: For other API errors
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

            # Extract and validate JSON
            response_dict = self.extract_json(response_text)
            return self.validate_response(response_dict)

        except anthropic.RateLimitError as e:
            logger.warning("anthropic_rate_limit", error=str(e))
            raise AIRateLimitError(f"Anthropic rate limit exceeded: {e}") from e
        except anthropic.APITimeoutError as e:
            logger.warning("anthropic_timeout", error=str(e))
            raise AITimeoutError(f"Anthropic API timeout: {e}") from e
        except anthropic.APIError as e:
            error_str = str(e).lower()
            if "quota" in error_str or "usage limit" in error_str:
                logger.error("anthropic_quota_exceeded", error=str(e))
                raise AIQuotaError(f"Anthropic quota exceeded: {e}") from e
            logger.error("anthropic_api_error", error=str(e))
            raise AIProviderError(f"Anthropic API error: {e}") from e
        except AIValidationError:
            raise  # Re-raise validation errors
        except Exception as e:
            logger.error("anthropic_unexpected_error", error_type=type(e).__name__, error=str(e))
            raise AIProviderError(f"Unexpected Anthropic error: {e}") from e

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

        # Get API key from config
        api_key = config.get("api_key")
        if not api_key:
            raise ValueError("api_key not found in ai_service.openai configuration")

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

        Raises:
            AIRateLimitError: If rate limit exceeded
            AITimeoutError: If request times out
            AIQuotaError: If API quota exceeded
            AIProviderError: For other API errors
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

            # Parse and validate JSON (OpenAI returns valid JSON with response_format)
            try:
                response_dict = json.loads(response_text)
            except json.JSONDecodeError:
                response_dict = self.extract_json(response_text)

            return self.validate_response(response_dict)

        except openai.RateLimitError as e:
            logger.warning("openai_rate_limit", error=str(e))
            raise AIRateLimitError(f"OpenAI rate limit exceeded: {e}") from e
        except openai.APITimeoutError as e:
            logger.warning("openai_timeout", error=str(e))
            raise AITimeoutError(f"OpenAI API timeout: {e}") from e
        except openai.APIError as e:
            error_str = str(e).lower()
            if "quota" in error_str or "insufficient" in error_str:
                logger.error("openai_quota_exceeded", error=str(e))
                raise AIQuotaError(f"OpenAI quota exceeded: {e}") from e
            logger.error("openai_api_error", error=str(e))
            raise AIProviderError(f"OpenAI API error: {e}") from e
        except AIValidationError:
            raise  # Re-raise validation errors
        except Exception as e:
            logger.error("openai_unexpected_error", error_type=type(e).__name__, error=str(e))
            raise AIProviderError(f"Unexpected OpenAI error: {e}") from e

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
