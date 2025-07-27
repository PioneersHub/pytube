# KI-hackathon vibe coded content pipeline

## Kurzüberblick

Dies hier war der Versuch, eine content pipeline zu vibe coden, die Talk Transkripte und Metadaten einliest und daraus verschiedene social media posts erstellt.
Ein anderer Teil des Teams hat sich mit der exakten Erstellung der posts beschäftigt, hier ging es mehr um die Pipeline und die Infrastruktur.

Plan war es, Supabase und n8n zu benutzen. Supabase für die Datenbank welche talks wie verarbeitet werden, welche Email notifications abgesetzt wurden etc.
n8n sollte für die tatsächliche pipeline sorgen.

## Zwischenfazit

Supabase hat sehr gut funktioniert, n8n hat kein gutes programmatisches Interface/MCP Server, das hat nicht so gut funktioniert.
Es kann sein, dass die n8n pipeline relativ einfach zu reparieren ist und Dinge dann größtenteils funktionieren, es kann aber auch sein, dass das jetzt 80% der Arbeit ist.

## Environment Variables

Der Code erwartet ein `.env` file mit den Variablen

```bash
export GEMINI_API_KEY=REDACTED
export SUPABASE_API_KEY=REDACTED
export SUPABASE_URL=REDACTED

# Pipeline configuration
export SOCIAL_MEDIA_OWNER_EMAIL=REDACTED
export LOCAL_FILE_BASE_PATH=REDACTED

export N8N_PW=REDACTED
export N8N_API_URL=REDACTED
export N8N_API_KEY=REDACTED
```
