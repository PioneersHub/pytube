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

## Alternatives

Other LLMs can be used via monkey patching `teaser_text` and `sized_text` in the `nlpserice` module.
