# Video Pipeline Requirements Document

## 1. Executive Summary

This document defines the requirements for an automated n8n pipeline that processes conference talk metadata and transcripts daily, generates content using AI agents, and manages the review/publication workflow.

## 2. System Overview

### 2.1 Pipeline Architecture

- **Orchestration**: n8n (self-hosted or cloud)
- **Database**: Supabase (PostgreSQL)
- **AI Processing**: OpenAI/Claude/other LLMs via API
- **Notifications**: Email system
- **Schedule**: Daily batch processing

### 2.2 Data Flow

1. Daily trigger reads local files (metadata + transcripts)
2. Check Supabase for unprocessed talks
3. Generate content via AI agents
4. Store generated content in Supabase
5. Send email notifications for review
6. Human approval updates status
7. Approved content ready for manual publishing

## 3. Database Schema (Supabase)

```sql
-- Main tracking table for talks
CREATE TABLE talks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    talk_id VARCHAR(10) UNIQUE NOT NULL, -- e.g., "PKZD8L"
    title TEXT NOT NULL,
    talk_date TIMESTAMP,
    youtube_url TEXT,
    processing_status VARCHAR(50) DEFAULT 'new',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Social media content tracking
CREATE TABLE social_content (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    talk_id VARCHAR(10) REFERENCES talks(talk_id),
    platform VARCHAR(50) NOT NULL, -- 'youtube', 'linkedin', 'twitter', 'facebook', 'instagram'
    content_type VARCHAR(50) NOT NULL, -- 'description', 'post', 'thread'
    generated_content TEXT,
    edited_content TEXT,
    status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'generated', 'reviewed', 'approved', 'scheduled', 'posted', 'failed'
    error_message TEXT,
    owner_email VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    reviewed_at TIMESTAMP,
    posted_at TIMESTAMP
);

-- Email notification queue
CREATE TABLE notification_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    talk_id VARCHAR(10) REFERENCES talks(talk_id),
    recipient_type VARCHAR(50), -- 'speaker', 'social_media_owner'
    recipient_email VARCHAR(255),
    notification_type VARCHAR(50), -- 'content_ready_for_review'
    sent BOOLEAN DEFAULT FALSE,
    sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Speaker information cache
CREATE TABLE speakers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    speaker_code VARCHAR(10) UNIQUE,
    name TEXT,
    email VARCHAR(255),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_talks_status ON talks(processing_status);
CREATE INDEX idx_social_content_status ON social_content(status);
CREATE INDEX idx_notifications_sent ON notification_queue(sent);
```

## 4. n8n Workflow Components

### 4.1 Daily Trigger

- **Schedule**: Daily at configured time (e.g., 2 AM UTC)
- **Type**: Cron trigger

### 4.2 File Processing Nodes

#### Node 1: Read Metadata Files

- **Type**: Local File System
- **Path**: `/Users/REDACTED/Documents/development/ki-garage-hackathon/pytube_data/pyconde-pydata-2025/pretalx_records/*.json`
- **Operation**: List and read JSON files

#### Node 2: Read Transcript Files

- **Type**: Local File System
- **Path Pattern**: `/Users/REDACTED/Documents/development/ki-garage-hackathon/pytube_data/pyconde-pydata-2025/transcriptions/*/*.txt`
- **Operation**: Match transcript to talk_id from folder name

### 4.3 Database Operations

#### Node 3: Check Existing Talks

- **Type**: Supabase
- **Operation**: Query talks table for new items
- **Logic**: Process only talks not in database or with status 'new'

#### Node 4: Insert New Talks

- **Type**: Supabase
- **Operation**: Insert talk metadata into talks table

### 4.4 AI Content Generation

#### Node 5: AI Agent Processor

- **Type**: HTTP Request / AI Service
- **For each platform**: youtube, linkedin, twitter, facebook, instagram
- **Input**:
  ```json
  {
    "talk_metadata": {
      /* from JSON file */
    },
    "transcript": "/* from transcript file */",
    "platform": "youtube",
    "template": "generic_youtube_description"
  }
  ```
- **Output**: Generated content text

### 4.5 Content Storage

#### Node 6: Store Generated Content

- **Type**: Supabase
- **Operation**: Insert into social_content table
- **Status**: Set to 'generated'

### 4.6 Notification System

#### Node 7: Queue Notifications

- **Type**: Supabase
- **Logic**:
  - If speaker email exists in metadata, queue speaker notification
  - Queue social media owner notification (configured in n8n)

#### Node 8: Send Email Notifications

- **Type**: Email (SMTP/SendGrid/etc.)
- **Template**: Review request with link to approval interface

### 4.7 Error Handling

#### Node 9: Error Logger

- **Type**: Supabase
- **Operation**: Update social_content with error_message
- **Notification**: Alert admin of failures

## 5. AI Agent Configuration

### 5.1 Generic Templates

#### YouTube Description Template

```
Title: [TALK_TITLE]

Speaker(s): [SPEAKER_NAMES]

Description:
[AI_GENERATED_SUMMARY]

Key Topics:
[AI_GENERATED_BULLET_POINTS]

About the Speaker(s):
[SPEAKER_BIOS]

Timestamps:
[AI_GENERATED_TIMESTAMPS]

Conference: [CONFERENCE_NAME]
Track: [TRACK_NAME]
Date: [TALK_DATE]

#python #conference #[RELEVANT_HASHTAGS]
```

#### LinkedIn Post Template

```
🎯 [AI_GENERATED_HOOK]

[AI_GENERATED_KEY_INSIGHT]

In this talk, [SPEAKER_NAME] explores [AI_GENERATED_TOPIC_SUMMARY]

Key takeaways:
[AI_GENERATED_TAKEAWAYS]

Watch the full talk: [YOUTUBE_URL]

#python #[CONFERENCE_HASHTAG] #[RELEVANT_HASHTAGS]
```

### 5.2 AI Processing Instructions

- Keep content professional and engaging
- Extract 3-5 key takeaways
- Generate timestamps for major topic changes
- Suggest relevant hashtags based on content
- Maintain speaker's technical credibility

## 6. Configuration Requirements

### 6.1 n8n Environment Variables

```
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_API_KEY=xxx
AI_API_KEY=xxx
SMTP_HOST=xxx
SMTP_USER=xxx
SMTP_PASS=xxx
SOCIAL_MEDIA_OWNER_EMAIL=xxx
REVIEW_APP_URL=https://xxx
LOCAL_FILE_BASE_PATH=/Users/REDACTED/Documents/development/ki-garage-hackathon/pytube_data
```

### 6.2 Configurable Parameters

- Processing schedule
- AI model selection per content type
- Temperature settings
- Maximum content lengths per platform
- Retry attempts and delays

## 7. User Interface Requirements

### 7.1 Review Interface (Future Phase)

- Web interface for content review
- Show original and generated content side-by-side
- Edit capabilities
- Approve/Reject buttons
- Bulk operations

### 7.2 Monitoring Dashboard (Future Phase)

- Pipeline execution status
- Processing statistics
- Error logs
- Content generation metrics

## 8. Success Criteria

### 8.1 Functional Requirements

- ✅ Process new talks daily automatically
- ✅ Generate content for all configured platforms
- ✅ Store all content with proper status tracking
- ✅ Send notifications to correct recipients
- ✅ Handle errors gracefully with logging

### 8.2 Performance Requirements

- Process 50+ talks per batch
- Complete generation within 30 minutes
- 95% success rate for content generation
- Email delivery within 5 minutes of generation

## 9. Security Considerations

- API keys stored securely in n8n
- Database access limited to pipeline service account
- No direct file system access from external sources
- Email addresses validated before sending
- Rate limiting on AI API calls

## 10. Future Enhancements

- Multi-language content generation
- A/B testing different templates
- Analytics integration for engagement tracking
- Direct publishing to platforms via APIs
- Speaker preference management
- Content scheduling optimization

---

**Document Version**: 1.0  
**Created**: 2025-01-26  
**Status**: Ready for Implementation
