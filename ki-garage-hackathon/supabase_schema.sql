-- Video Pipeline Database Schema for Supabase
-- Version 1.0
-- Created: 2025-01-26

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Drop existing tables if they exist (be careful in production!)
DROP TABLE IF EXISTS notification_queue CASCADE;
DROP TABLE IF EXISTS social_content CASCADE;
DROP TABLE IF EXISTS speakers CASCADE;
DROP TABLE IF EXISTS talks CASCADE;

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
CREATE INDEX idx_social_content_talk_platform ON social_content(talk_id, platform);
CREATE INDEX idx_notifications_sent ON notification_queue(sent);

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Add triggers to update updated_at automatically
CREATE TRIGGER update_talks_updated_at BEFORE UPDATE ON talks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_social_content_updated_at BEFORE UPDATE ON social_content
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_speakers_updated_at BEFORE UPDATE ON speakers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Add some helpful views
CREATE VIEW v_pending_content AS
SELECT 
    t.talk_id,
    t.title,
    t.talk_date,
    sc.platform,
    sc.content_type,
    sc.generated_content,
    sc.status,
    sc.created_at
FROM talks t
JOIN social_content sc ON t.talk_id = sc.talk_id
WHERE sc.status IN ('pending', 'generated')
ORDER BY sc.created_at DESC;

CREATE VIEW v_notification_status AS
SELECT 
    t.talk_id,
    t.title,
    nq.recipient_type,
    nq.recipient_email,
    nq.sent,
    nq.sent_at,
    nq.created_at
FROM talks t
JOIN notification_queue nq ON t.talk_id = nq.talk_id
ORDER BY nq.created_at DESC;

-- Grant permissions (adjust based on your Supabase setup)
-- These are examples - Supabase handles permissions differently
-- You'll need to set up Row Level Security (RLS) policies in Supabase dashboard

-- Sample RLS policies (execute these in Supabase SQL editor after enabling RLS)
/*
ALTER TABLE talks ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_content ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE speakers ENABLE ROW LEVEL SECURITY;

-- Example policy: Allow authenticated users to read all data
CREATE POLICY "Allow authenticated read access" ON talks
    FOR SELECT USING (auth.role() = 'authenticated');

CREATE POLICY "Allow authenticated read access" ON social_content
    FOR SELECT USING (auth.role() = 'authenticated');

-- Example policy: Allow service role full access
CREATE POLICY "Allow service role full access" ON talks
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Allow service role full access" ON social_content
    FOR ALL USING (auth.role() = 'service_role');
*/