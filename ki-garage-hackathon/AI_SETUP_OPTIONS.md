# AI Setup Options for Content Generation

You have several options for the AI content generation part of the pipeline:

## Option 1: OpenAI API (Recommended)

### Getting an API Key:
1. Go to https://platform.openai.com/
2. Sign up or log in
3. Go to API Keys: https://platform.openai.com/api-keys
4. Create a new key
5. Add to n8n credentials

### Costs:
- GPT-4: ~$0.03 per 1K tokens
- GPT-3.5: ~$0.001 per 1K tokens
- Each talk will use ~2-3K tokens total

## Option 2: Use Your Existing Gemini API

Since you already have a Gemini API key in your .env file, we can modify the workflow to use Google's Gemini instead of OpenAI.

### To use Gemini:
1. In n8n, change the OpenAI nodes to HTTP Request nodes
2. Use the Gemini API endpoint
3. Your existing key: Already in .env as GEMINI_API_KEY

## Option 3: Local LLM (Ollama)

### Setup:
```bash
# Install Ollama
brew install ollama

# Download a model
ollama pull llama2
# or
ollama pull mistral

# Start Ollama
ollama serve
```

### In n8n:
- Use HTTP Request nodes
- Point to: http://localhost:11434/api/generate

## Option 4: Mock AI for Testing

For initial testing, we can use a simple template-based approach without AI:

```javascript
// In n8n Code node
const mockDescription = `
Title: ${items[0].json.title}

Speaker(s): ${items[0].json.speakers.map(s => s.name).join(', ')}

Description:
This talk explores ${items[0].json.title.toLowerCase()}. 
${items[0].json.abstract}

Conference: PyCon DE & PyData 2025
Track: ${items[0].json.track}
`;

return [{json: {content: mockDescription}}];
```

## Quick Decision Guide:

- **For production use**: OpenAI or Gemini
- **For testing**: Mock AI or Ollama
- **For cost savings**: Ollama (free but lower quality)
- **Already have**: Use your Gemini API key

Let me know which option you prefer and I can help modify the workflow!