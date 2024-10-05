# NLP Services

The OpenAI API is used to generate descriptions from the information retrieved from Pretalx.

Attributes added to the session records:

| Record         | Description                                |
|----------------|--------------------------------------------|
| sm_teaser_text | A short engaging text with about 50 tokens |
| sm_short_text  | A short description with about 100 tokens  |
| sm_long_text   | A short description with about300 tokens   |

## Setup

Add your API key for Open AI to `config_local.yaml`.

```yaml
openai:
  api_key: "your-api-key..."
```

The API key can be found [in your OpenAI account](https://platform.openai.com/api-keys)

## Prompts

Prompts can be adjusted in the config. Add custom prompts to `config_local.yaml`.

```yaml
prompts:
  teaser: >
    You are an expert editor and your task is to write one short teaser sentence to encourage people to watch
    the video based on the title and text.  The teaser should be a short sentence that is catchy and engaging.
    Use a professional tone. Start with 'Watch'.
  # note there is a placeholder to instruct about the desired the length: {max_tokens}
  description: >
    You are an expert editor and your task is to create a continuous text with about {max_tokens} tokens.
    The text describes the talk and should be concise and informative please. Mention the speaker names,
    jobs and companies. Never use the verb 'delve'. Make sure only to mention jobs and companies
    if they are mentioned in the text. 
```


## Alternatives

Other LLMs can be used via monkey patching `teaser_text` and `sized_text` in the `nlpserice` module.
