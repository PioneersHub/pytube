# Gemini Pipeline Setup Guide

This is the complete, working n8n pipeline using Google's Gemini AI.

## Features

✅ **Reads from local files** (metadata + transcripts)  
✅ **Uses Gemini AI** for content generation  
✅ **Stores in Supabase** with proper status tracking  
✅ **Queues notifications** for review  
✅ **Updates talk status** after processing  

## Import Instructions

1. **In n8n**, create a new workflow
2. Click **⋮** menu → **Import from File**
3. Select `n8n_gemini_pipeline.json`
4. Click **Save**

## Configuration

The workflow includes all necessary variables:
- ✅ `SUPABASE_URL` - Already set
- ✅ `GEMINI_API_KEY` - Already set
- ✅ `LOCAL_FILE_BASE_PATH` - Already set
- ✅ `SOCIAL_MEDIA_OWNER_EMAIL` - Already set

## How It Works

1. **Trigger**: Manual or daily schedule
2. **Get New Talks**: Fetches talks with status "new" from Supabase
3. **Read Files**: 
   - Reads metadata from JSON files
   - Finds and reads transcript TXT files
4. **Generate Content**:
   - YouTube descriptions via Gemini
   - LinkedIn posts via Gemini
5. **Store & Notify**:
   - Saves to Supabase
   - Queues email notifications
   - Updates talk status to "processed"

## Testing

1. Click **Execute Workflow**
2. Watch the execution:
   - Green = Success
   - Orange = Warning
   - Red = Error
3. Check Supabase for generated content

## Troubleshooting

### "File not found" errors
The workflow will try to read metadata files. If they don't exist for dummy data, that's OK - it will continue with basic info.

### "No new talks"
Change talk status in Supabase back to "new":
```sql
UPDATE talks SET processing_status = 'new' WHERE talk_id LIKE 'DUMMY%';
```

### Gemini API errors
- Check API key is valid
- Verify you have API quota remaining

## What Gets Generated

### YouTube Description Example:
```
Building Scalable Python Applications with AsyncIO

Speaker(s): Dr. Jane Smith

Description:
[AI-generated engaging summary]

Key Topics:
• AsyncIO fundamentals
• Event loop architecture
• Performance optimization
• Real-world examples

Conference: PyCon DE & PyData 2025
Track: Advanced Python

#python #pycon2025 #pydata #asyncio
```

### LinkedIn Post Example:
```
🚀 Just discovered an incredible talk on AsyncIO!

[AI-generated insight about the talk]

Key takeaways:
✅ [Takeaway 1]
✅ [Takeaway 2]
✅ [Takeaway 3]

Watch the full talk: [URL]

#python #pycon2025 #asyncprogramming
```

## Next Steps

1. **Test with dummy data** first
2. **Process real talks** by changing their status to "new"
3. **Enable daily schedule** when ready for production
4. **Set up email sending** workflow (separate)