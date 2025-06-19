"""
OpenAI integration for generating text descriptions.

Configuration in config.yaml:
    openai:
        api_key: "your-api-key"
        model: "gpt-3.5-turbo"  # or gpt-4, gpt-4-turbo, etc.
        temperature:
            teaser: 0.7         # Lower = more focused/deterministic
            description: 0.9    # Higher = more creative/random
"""

from openai import OpenAI

from manager import conf

client = OpenAI(api_key=conf.openai.api_key)


def teaser_text(text, max_tokens=50, temperature=None):
    """A call to watch with a super short teaser"""
    # Use temperature from config if not specified
    if temperature is None:
        temperature = conf.openai.get("temperature", {}).get("teaser", 0.7)

    response = client.chat.completions.create(
        model=conf.openai.get("model", "gpt-3.5-turbo"),
        messages=[
            {"role": "system", "content": conf.prompts.teaser},
            {"role": "user", "content": text},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    gtp_text = response.choices[0].message.content
    return gtp_text


def sized_text(text, max_tokens=100, temperature=None):
    # Use temperature from config if not specified
    if temperature is None:
        temperature = conf.openai.get("temperature", {}).get("description", 0.9)

    response = client.chat.completions.create(
        model=conf.openai.get("model", "gpt-3.5-turbo"),
        messages=[
            {
                "role": "system",
                "content": conf.prompts.description.format({"max_tokens": max_tokens}),
            },
            {"role": "user", "content": text},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    gtp_text = response.choices[0].message.content
    return gtp_text
