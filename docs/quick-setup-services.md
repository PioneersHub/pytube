# Quick Setup: AI & Social Media Services

## 🚀 Fastest Setup (Recommended for beginners)

### 1. OpenAI (Easiest AI setup)
```yaml
# In config_local.yaml
ai_service:
  provider: "openai"
  openai:
    api_key: "sk-..."  # Get from platform.openai.com/api-keys
    model: "gpt-4-turbo"
```
**Time to setup**: 5 minutes  
**Cost**: ~$0.10 per conference

### 2. LinkedIn (If you have company access)
```yaml
social_media_service: "linkedin"
linkedin:
  access_token: "..."  # Complex OAuth process
  company_id: "..."    # From company page URL
```
**Time to setup**: 30-60 minutes  
**Cost**: Free

### 3. Bluesky (Easiest social setup)
```yaml
social_media_service: "bluesky"
bluesky:
  handle: "you.bsky.social"
  app_password: "xxxx-xxxx-xxxx-xxxx"  # From Settings → App Passwords
```
**Time to setup**: 2 minutes  
**Cost**: Free

---

## 🎯 Decision Matrix

### Which AI Service?

| Service | Best For | Setup Difficulty | Cost |
|---------|----------|-----------------|------|
| **OpenAI** | General use, proven quality | Easy | $$ |
| **Anthropic** | Longer contexts, nuanced text | Easy | $$$ |
| **Google** | Free tier, experimentation | Easy | $ |
| **Cohere** | Budget option | Easy | $ |

### Which Social Platform?

| Platform | Best For | Setup Difficulty | Requirements |
|----------|----------|-----------------|--------------|
| **LinkedIn** | Professional audience | Hard | Company page |
| **Twitter/X** | Wide reach | Medium | Paid API ($100/mo) |
| **Mastodon** | Open source community | Easy | Choose instance |
| **Bluesky** | Growing platform | Very Easy | Just username |

---

## 📋 Minimal Working Config

```yaml
# config_local.yaml - Copy this and add your keys

# Event configuration
pretalx:
  event_slug: "your-event-2025"

# AI Service (pick one)
ai_service:
  provider: "openai"
  openai:
    api_key: "sk-..."

# Social Media (pick one)  
social_media_service: "bluesky"
bluesky:
  handle: "yourname.bsky.social"
  app_password: "xxxx-xxxx-xxxx-xxxx"
```

---

## 🔧 Testing Your Setup

### Test AI Service
```bash
# After configuring, test with:
pytube records fetch --limit 1
# This will use AI to generate descriptions
```

### Test Social Media
```bash
# Create a test post:
echo '{"post": "Test post from PyTube"}' > test_post.json
# Then use publisher module to post
```

---

## 💡 Pro Tips

1. **Start with OpenAI + Bluesky** - Easiest combination
2. **Use GPT-3.5-turbo** - 10x cheaper than GPT-4
3. **Test with 1-2 videos first** - Don't process entire conference immediately
4. **Set up cost alerts** - In OpenAI/Anthropic dashboards
5. **Use app passwords** - Never use your main password

---

## 🆘 Need Help?

- Check detailed guide: `docs/api-credentials.md`
- Common errors: `docs/troubleshooting.md`
- Ask in issues: github.com/yourusername/pytube/issues