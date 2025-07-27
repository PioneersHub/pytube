# n8n Quick Start Guide

## 1. Start n8n

Open a new terminal window and run:

```bash
./start_n8n.sh
```

Or directly:

```bash
n8n start
```

## 2. Access n8n

Open your browser and go to: **http://localhost:5678**

### First Time Setup:

1. Create an account (email + password)
2. Skip the survey if prompted

## 3. Import the Workflow

1. Click **"Add workflow"** (+ button)
2. Click the three dots menu (⋮) → **"Import from File"**
3. Select `n8n_workflow_template.json` from this directory
4. Click **"Save"** to save the workflow

## 4. Configure Credentials

You'll need to add three credentials. Go to **Settings** → **Credentials** → **Add credential**:

### a) Supabase API

- Type: **Supabase API**
- Name: `Supabase API`
- Host: `https://fjoinugnymseappjxrwu.supabase.co`
- Service Role API Key: Use your key from .env file

### b) OpenAI API (for content generation)

- Type: **OpenAI API**
- Name: `OpenAI API`
- API Key: Your OpenAI API key

**Don't have an OpenAI key?** You can:

- Get one at https://platform.openai.com/api-keys
- Or modify the workflow to use a different AI provider

### c) Email (SMTP) - Optional for now

- Type: **SMTP**
- Name: `Email SMTP`
- Can configure later when ready for notifications

## 5. Update Workflow Settings

After importing, you'll need to:

1. **Fix File Paths**:

   - Click on "List Metadata Files" node
   - Update the path if it shows an error
   - Should be: `/Users/REDACTED/Documents/development/ki-garage-hackathon/pytube_data/pyconde-pydata-2025/pretalx_records`

2. **Connect Credentials**:
   - Click on each Supabase node
   - Select "Supabase API" from the credential dropdown
   - Click on OpenAI nodes
   - Select "OpenAI API" from the credential dropdown

## 6. Test the Workflow

1. Click **"Execute Workflow"** button
2. Watch the execution progress
3. Check for any errors in red nodes
4. View results in your Supabase dashboard

## 7. Enable Automated Runs

Once testing is successful:

1. Click on the "Daily Trigger" node
2. Toggle **"Active"** to ON
3. Save the workflow

## Troubleshooting

### "File not found" errors

- Verify the file paths match your local setup
- Check that files exist in the specified directories

### "Invalid credentials" errors

- Double-check your API keys in the credential settings
- Make sure you're using the correct Supabase project URL

### "No new talks found"

- This is normal if all talks are already processed
- Check Supabase `talks` table to see existing entries

## View Generated Content

Check your Supabase dashboard:

- Table: `social_content` - See all generated content
- Table: `notification_queue` - See pending notifications
- View: `v_pending_content` - See content awaiting review
