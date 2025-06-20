# PyTube

Utilize [Pretalx](https://github.com/pretalx/pretalx) data to manage and release your conference videos on YouTube.

## Main Features

Manage and update metadata for your conference videos on YouTube using data from Pretalx:

* **Video Management on YouTube:**
    * Automated video descriptions from Pretalx data
    * Scheduled publishing dates
    * Multi-channel support for different tracks
    * Release status monitoring

* **AI-Powered Content Generation:**
    * Support for multiple AI providers: OpenAI (GPT-3.5/4), Anthropic Claude, Google Gemini, Cohere
    * Automated teaser and description generation
    * Configurable temperature settings for creativity control

* **Multi-Platform Social Media:**
    * Post to LinkedIn, Twitter/X, Mastodon, or Bluesky
    * Platform-specific formatting (character limits)
    * Automated posting when videos go live

* **Additional Features:**
    * Email notifications to speakers
    * Event-based directory structure for multi-conference support
    * AI-friendly CLI with structured JSON responses
    * Comprehensive setup wizard

## Quick Start

1. **Install PyTube:**
   ```bash
   pip install -e .
   ```

2. **Run Setup Wizard:**
   ```bash
   pytube setup
   ```

3. **Configure Services** (in `config_local.yaml`):
   ```yaml
   # AI Service (for descriptions)
   ai_service: "openai"
   openai:
     api_key: "sk-..."
   
   # Social Media (for posts)
   social_media_service: "bluesky" 
   bluesky:
     handle: "you.bsky.social"
     app_password: "xxxx-xxxx-xxxx-xxxx"
   ```

4. **Process Conference:**
   ```bash
   pytube enhanced   # Enhanced interactive mode (recommended)
   # or
   pytube assistant  # Standard interactive mode
   # or
   pytube records fetch && pytube youtube update  # Manual commands
   ```

## Documentation

* **Full Documentation:** [pioneershub.github.io/pytube](https://pioneershub.github.io/pytube/)
* **API Credentials Guide:** [docs/api-credentials.md](docs/api-credentials.md)
* **Quick Setup:** [docs/quick-setup-services.md](docs/quick-setup-services.md)
* **CLI Reference:** [docs/cli-reference.md](docs/cli-reference.md)

Thanks to [Pioneers Hub gGmbH](https://pioneershub.org) for the support and the funding for the idea.
