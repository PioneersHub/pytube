from openai import OpenAI

from pytube import conf

client = OpenAI(api_key=conf.openai.api_key)


def teaser_text(text, max_tokens=50, temperature=0.7):
    """A call to watch with a super short teaser"""
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",  # Use GPT-4 or GPT-3.5-turbo
        messages=[
            {"role": "system",
             "content": conf.prompts.teaser},
            {"role": "user", "content": text},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    gtp_text = response.choices[0].message.content
    return gtp_text


def sized_text(text, max_tokens=100, temperature=0.9):
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",  # Use GPT-4 or GPT-3.5-turbo
        messages=[
            {"role": "system",
             "content": conf.prompts.description.format({"max_tokens": max_tokens})
             },
            {"role": "user", "content": text},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    gtp_text = response.choices[0].message.content
    return gtp_text
