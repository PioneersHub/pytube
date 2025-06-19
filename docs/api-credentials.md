# API Credentials Guide

This guide explains how to obtain API credentials for all supported AI and social media services in PyTube.

## Table of Contents
- [AI Services](#ai-services)
  - [OpenAI](#openai)
  - [Anthropic Claude](#anthropic-claude)
  - [Google Gemini](#google-gemini)
  - [Cohere](#cohere)
- [Social Media Platforms](#social-media-platforms)
  - [LinkedIn](#linkedin)
  - [Twitter/X](#twitterx)
  - [Mastodon](#mastodon)
  - [Bluesky](#bluesky)

---

## AI Services

### OpenAI

**Required**: `api_key`

1. **Sign up**: Go to [platform.openai.com](https://platform.openai.com) and create an account
2. **API Keys**: Navigate to [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
3. **Create Key**: Click "Create new secret key"
4. **Copy Key**: Save the key immediately (it won't be shown again)
5. **Billing**: Add payment method at [platform.openai.com/account/billing](https://platform.openai.com/account/billing)

**Configuration**:
```yaml
ai_service: "openai"
openai:
  api_key: "sk-..."
  model: "gpt-3.5-turbo"  # or gpt-4, gpt-4o
  organization: "org-..."  # Optional
```

**Pricing**: 
- GPT-3.5-turbo: ~$0.002 per 1K tokens
- GPT-4: ~$0.03-0.06 per 1K tokens
- Check current pricing at [openai.com/pricing](https://openai.com/pricing)

### Anthropic Claude

**Required**: `api_key`

1. **Sign up**: Go to [console.anthropic.com](https://console.anthropic.com) and create an account
2. **API Keys**: Navigate to Account Settings → API Keys
3. **Create Key**: Click "Create Key"
4. **Copy Key**: Save the key immediately
5. **Credits**: Add credits or payment method in billing section

**Configuration**:
```yaml
ai_service: "anthropic"
anthropic:
  api_key: "sk-ant-..."
  model: "claude-3-sonnet-20240229"  # or claude-3-opus-20240229, claude-3-haiku-20240307
  max_tokens: 1000
```

**Pricing**:
- Claude 3 Haiku: ~$0.25 per 1M tokens (input), $1.25 per 1M tokens (output)
- Claude 3 Sonnet: ~$3 per 1M tokens (input), $15 per 1M tokens (output)
- Claude 3 Opus: ~$15 per 1M tokens (input), $75 per 1M tokens (output)

### Google Gemini

**Required**: `api_key`

1. **Sign up**: Go to [makersuite.google.com](https://makersuite.google.com) (Google AI Studio)
2. **Get API Key**: Click on "Get API key" in the left sidebar
3. **Create Key**: Choose "Create API key in new project" or select existing project
4. **Copy Key**: Save the generated API key
5. **Enable**: The Gemini API is automatically enabled

**Configuration**:
```yaml
ai_service: "google"
google:
  api_key: "AIza..."
  model: "gemini-pro"  # or gemini-pro-vision for multimodal
  safety_settings:
    harassment: "BLOCK_MEDIUM_AND_ABOVE"
    hate_speech: "BLOCK_MEDIUM_AND_ABOVE"
```

**Pricing**:
- Gemini Pro: Free tier available (60 queries per minute)
- Paid tier: $0.00025 per 1K characters (input), $0.0005 per 1K characters (output)

### Cohere

**Required**: `api_key`

1. **Sign up**: Go to [dashboard.cohere.com](https://dashboard.cohere.com) and create an account
2. **API Keys**: Navigate to API Keys section
3. **Create Key**: Click "Create Trial Key" or "Create Production Key"
4. **Copy Key**: Save the key immediately
5. **Upgrade**: Trial keys have limited usage; upgrade for production use

**Configuration**:
```yaml
ai_service: "cohere"
cohere:
  api_key: "..."
  model: "command"  # or command-light, command-nightly
```

**Pricing**:
- Trial: Free with limited usage
- Production: Starting at $0.40 per 1M tokens
- Check [cohere.com/pricing](https://cohere.com/pricing) for details

---

## Social Media Platforms

### LinkedIn

**Required**: `access_token`, `company_id` (optional)

LinkedIn uses OAuth 2.0, which is complex for personal use. Here are two approaches:

#### Option 1: Using LinkedIn Developer App (Recommended for organizations)

1. **Create App**: Go to [linkedin.com/developers](https://www.linkedin.com/developers/) and create an app
2. **Verify App**: Complete verification process (requires company page admin access)
3. **Products**: Request access to "Share on LinkedIn" and "Marketing Developer Platform"
4. **OAuth Flow**: Implement OAuth 2.0 flow to get access token
5. **Company ID**: Find in your LinkedIn company page URL

#### Option 2: Using Third-Party Tools (Easier for personal use)

1. Use tools like [LinkedIn API Console](https://www.linkedin.com/developers/tools/api-console)
2. Or use Postman's LinkedIn collection to generate tokens
3. Note: Personal access tokens may have limited scope

**Configuration**:
```yaml
social_media_service: "linkedin"
linkedin:
  access_token: "AQX..."
  refresh_token: "..."  # Optional, for auto-refresh
  client_id: "..."      # From your app
  client_secret: "..."  # From your app
  company_id: "12345"   # Optional, for company posts
```

### Twitter/X

**Required**: `api_key`, `api_secret`, `access_token`, `access_token_secret`

1. **Developer Account**: Apply at [developer.twitter.com](https://developer.twitter.com)
2. **Create Project**: Once approved, create a new project and app
3. **Keys**: In your app settings, find:
   - API Key (Consumer Key)
   - API Secret (Consumer Secret)
4. **Access Tokens**: Generate Access Token and Secret
5. **Permissions**: Set app permissions to "Read and Write"

**Configuration**:
```yaml
social_media_service: "twitter"
twitter:
  api_key: "..."         # Also called Consumer Key
  api_secret: "..."      # Also called Consumer Secret
  access_token: "..."
  access_token_secret: "..."
  bearer_token: "..."    # Optional, for app-only auth
```

**Note**: Twitter API access now requires paid tier ($100/month for Basic)

### Mastodon

**Required**: `access_token`, `instance_url`

1. **Choose Instance**: Select your Mastodon instance (e.g., mastodon.social, fosstodon.org)
2. **Create App**: Go to Preferences → Development → New Application
3. **Permissions**: Select required scopes:
   - `write:statuses` (for posting)
   - `write:media` (for images)
4. **Create**: Submit and create the application
5. **Access Token**: Copy the access token from the app details

**Configuration**:
```yaml
social_media_service: "mastodon"
mastodon:
  instance_url: "https://mastodon.social"  # Your instance
  access_token: "..."
  visibility: "public"  # or unlisted, private, direct
```

### Bluesky

**Required**: `handle`, `app_password`

1. **Account**: Create account at [bsky.app](https://bsky.app)
2. **App Password**: Go to Settings → App Passwords
3. **Create**: Click "Add App Password"
4. **Name**: Give it a descriptive name (e.g., "PyTube")
5. **Copy**: Save the generated app password

**Configuration**:
```yaml
social_media_service: "bluesky"
bluesky:
  handle: "yourhandle.bsky.social"  # Your full handle
  app_password: "xxxx-xxxx-xxxx-xxxx"  # Generated app password
```

**Note**: Never use your main account password; always use app-specific passwords

---

## Security Best Practices

1. **Never commit credentials**: Always use `config_local.yaml` (git-ignored)
2. **Use environment variables**: For production deployments
3. **Rotate keys regularly**: Especially for production use
4. **Limit permissions**: Only grant necessary scopes/permissions
5. **Monitor usage**: Check API dashboards for unusual activity

## Environment Variables Alternative

Instead of storing in config files, you can use environment variables:

```bash
# AI Services
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."

# Social Media
export LINKEDIN_ACCESS_TOKEN="..."
export TWITTER_API_KEY="..."
```

Then reference in your config:
```yaml
openai:
  api_key: ${OPENAI_API_KEY}
```

## Troubleshooting

### Common Issues

1. **"Invalid API Key"**: 
   - Check for extra spaces or quotes
   - Ensure key hasn't been revoked
   - Verify you're using the correct service

2. **"Rate limit exceeded"**:
   - Check your plan limits
   - Implement exponential backoff
   - Consider upgrading tier

3. **"Insufficient permissions"**:
   - Review OAuth scopes (social media)
   - Check API product access (LinkedIn)
   - Verify app permissions

4. **"Configuration not found"**:
   - Ensure config_local.yaml exists
   - Check YAML formatting
   - Verify service name spelling

## Cost Estimation

For a typical conference with 50 talks:
- **AI Costs**: ~$5-20 depending on model choice
- **Social Media**: Usually free (except Twitter Basic API)

## Support Links

- **OpenAI**: [help.openai.com](https://help.openai.com)
- **Anthropic**: [support.anthropic.com](https://support.anthropic.com)
- **Google AI**: [ai.google.dev/support](https://ai.google.dev/support)
- **Cohere**: [docs.cohere.com](https://docs.cohere.com)
- **LinkedIn**: [linkedin.com/help/linkedin](https://www.linkedin.com/help/linkedin)
- **Twitter**: [developer.twitter.com/support](https://developer.twitter.com/en/support)
- **Mastodon**: Instance-specific support
- **Bluesky**: [blueskyweb.xyz/support](https://blueskyweb.xyz/support)