from openai import OpenAI
from src import conf

client = OpenAI(api_key=conf.openai.api_key)


def teaser_text(text, max_tokens=50, temperature=0.7):
    """A call to watch with a super short teaser"""
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",  # Use GPT-4 or GPT-3.5-turbo
        messages=[
            {"role": "system",
             "content": "You are an expert editor and your task is to write one short teaser sentence"
                        " to encourage people to watch the video based on the title and text. "
                        "The teaser should be a short sentence that is catchy and engaging. "
                        "Use a professional tone."
                        "Start with 'Watch'."},
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
             "content": f"You are an expert editor and your task is to create a continuous text "
                        f"with about {max_tokens} tokens. "
                        "The text describes the talk and should be concise and informative please. "
                        "Mention the speaker names, jobs and companies. Do not use the word 'delve'."
                        "Make sure only to mention jobs and companies if they are mentioned in the text. "
             },
            {"role": "user", "content": text},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    gtp_text = response.choices[0].message.content
    return gtp_text
