# PyTube Pipeline Setup Guide

This guide will help you set up the automated content generation pipeline using n8n and Supabase.

## Prerequisites

- Python 3.8+ installed
- n8n instance (self-hosted or cloud)
- Supabase account (free tier works)
- OpenAI API key (or other LLM provider)
- SMTP server access for emails

## Step 1: Set up Supabase Database

### 1.1 Create a Supabase Project

1. Go to [https://app.supabase.com/](https://app.supabase.com/)
2. Create a new project
3. Save your project URL and API keys

### 1.2 Create Database Tables

1. In your Supabase dashboard, go to **SQL Editor**
2. Copy the entire content of `supabase_schema.sql`
3. Paste and run the SQL script
4. You should see all tables created successfully

### 1.3 Test Database Connection

```bash
# Install dependencies
pip install supabase python-dotenv

# Run the setup script
python setup_supabase.py
```

Follow the prompts to:

- Enter your Supabase credentials
- Test the connection
- Optionally insert test data

## Step 2: Configure n8n

### 2.1 Install n8n (if not already installed)

**Option A: Using npm**

```bash
npm install n8n -g
n8n start
```

**Option B: Using Docker**

```bash
docker run -it --rm \
  --name n8n \
  -p 5678:5678 \
  -v ~/.n8n:/home/node/.n8n \
  n8nio/n8n
```

### 2.2 Access n8n

1. Open browser to `http://localhost:5678`
2. Create your n8n account (first time only)

### 2.3 Set up Credentials

In n8n, go to **Credentials** and add:

#### Supabase Credentials

- Type: **Supabase API**
- Name: `Supabase API`
- URL: Your Supabase project URL
- Service Role API Key: Your Supabase API key

#### OpenAI Credentials (or your preferred LLM)

- Type: **OpenAI API**
- Name: `OpenAI API`
- API Key: Your OpenAI API key

#### Email Credentials

- Type: **SMTP**
- Name: `Email SMTP`
- Host: Your SMTP server
- Port: 587 (or your SMTP port)
- User: Your email
- Password: Your email password

### 2.4 Set Environment Variables

In n8n settings or your deployment:

```bash
# Required environment variables
LOCAL_FILE_BASE_PATH=/Users/REDACTED/Documents/development/ki-garage-hackathon/pytube_data
SOCIAL_MEDIA_OWNER_EMAIL=your-email@example.com
REVIEW_APP_URL=https://your-review-app.com  # For future use
```

## Step 3: Import the Workflow

### 3.1 Import Template

1. In n8n, click **Workflows** → **Add Workflow**
2. Click the three dots menu → **Import from File**
3. Select `n8n_workflow_template.json`
4. The workflow will be imported

### 3.2 Configure Workflow Nodes

After import, you need to:

1. **Update file paths** in the workflow to match your local setup
2. **Select credentials** for each node that requires them:
   - Supabase nodes → Select your Supabase credentials
   - OpenAI nodes → Select your OpenAI credentials
   - Email nodes → Select your SMTP credentials

### 3.3 Test Individual Nodes

1. Click on each node
2. Click **Execute Node** to test individually
3. Fix any errors before proceeding

## Step 4: Create Email Notification Workflow

Create a separate workflow for sending emails:

### 4.1 Email Sender Workflow

1. Create new workflow called "Email Notifications"
2. Add nodes:
   - **Interval Trigger** (every 5 minutes)
   - **Supabase** - Query notification_queue where sent = false
   - **Email** - Send notification
   - **Supabase** - Update notification_queue set sent = true

## Step 5: Testing the Pipeline

### 5.1 Manual Test

1. In the main workflow, click **Execute Workflow**
2. Monitor the execution for any errors
3. Check Supabase tables for generated content

### 5.2 Verify Results

Check in Supabase:

```sql
-- View generated content
SELECT * FROM social_content WHERE status = 'generated';

-- View pending notifications
SELECT * FROM notification_queue WHERE sent = false;
```

## Step 6: Production Deployment

### 6.1 Enable Schedule

1. In the workflow, click on the **Daily Trigger** node
2. Toggle **Active** to enable scheduled execution
3. Save the workflow

### 6.2 Monitor Executions

- Check n8n execution history regularly
- Set up error notifications in n8n settings
- Monitor Supabase for failed content generation

## Troubleshooting

### Common Issues

1. **File not found errors**

   - Verify LOCAL_FILE_BASE_PATH is correct
   - Check file permissions
   - Ensure transcript folder naming matches pattern

2. **Supabase connection errors**

   - Verify credentials are correct
   - Check if RLS is disabled or policies are set
   - Use service role key, not anon key

3. **AI generation failures**

   - Check API key validity
   - Monitor rate limits
   - Verify prompt length < token limits

4. **Email not sending**
   - Verify SMTP credentials
   - Check firewall/port access
   - Test with simple email first

### Debug Mode

To debug issues:

1. Add **Debug** nodes after problematic nodes
2. Use **Set** nodes to inspect data
3. Check n8n execution logs

## Next Steps

1. **Create Review Interface**

   - Build web app for content review
   - Connect to Supabase
   - Allow editing and approval

2. **Add More Platforms**

   - Extend workflow for Twitter, Facebook, Instagram
   - Add platform-specific templates

3. **Enhance AI Prompts**

   - Fine-tune prompts for better output
   - Add few-shot examples
   - Implement prompt versioning

4. **Analytics Integration**
   - Track content performance
   - A/B test different templates
   - Optimize based on engagement

## Support

- n8n Documentation: https://docs.n8n.io/
- Supabase Documentation: https://supabase.com/docs
- Create issues in the project repository for bugs

---

Remember to keep your API keys secure and never commit them to version control!
