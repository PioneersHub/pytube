#!/usr/bin/env python3
"""
Test Supabase data operations
"""

import os
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client
import json

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_API_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

print("🚀 Testing Supabase Data Operations\n")

# Test 1: Insert a test talk
print("1️⃣ Inserting test talk...")
try:
    test_talk = {
        "talk_id": "TEST001",
        "title": "Test Talk: Introduction to Pipeline Automation",
        "talk_date": datetime.now().isoformat(),
        "processing_status": "new"
    }
    
    result = supabase.table("talks").insert(test_talk).execute()
    print("✅ Test talk inserted successfully")
    print(f"   ID: {result.data[0]['id']}")
except Exception as e:
    print(f"❌ Error inserting talk: {e}")

# Test 2: Insert test social content
print("\n2️⃣ Inserting test social content...")
try:
    test_content = {
        "talk_id": "TEST001",
        "platform": "youtube",
        "content_type": "description",
        "generated_content": "This is a test YouTube description for the pipeline test.",
        "status": "generated",
        "owner_email": os.getenv("SOCIAL_MEDIA_OWNER_EMAIL", "test@example.com")
    }
    
    result = supabase.table("social_content").insert(test_content).execute()
    print("✅ Test social content inserted successfully")
except Exception as e:
    print(f"❌ Error inserting social content: {e}")

# Test 3: Query the data back
print("\n3️⃣ Querying data...")
try:
    talks = supabase.table("talks").select("*").eq("talk_id", "TEST001").execute()
    print("✅ Retrieved test talk:")
    print(json.dumps(talks.data, indent=2, default=str))
    
    content = supabase.table("social_content").select("*").eq("talk_id", "TEST001").execute()
    print("\n✅ Retrieved social content:")
    print(json.dumps(content.data, indent=2, default=str))
except Exception as e:
    print(f"❌ Error querying data: {e}")

# Test 4: Test notification queue
print("\n4️⃣ Testing notification queue...")
try:
    notification = {
        "talk_id": "TEST001",
        "recipient_type": "social_media_owner",
        "recipient_email": "test@example.com",
        "notification_type": "content_ready_for_review"
    }
    
    result = supabase.table("notification_queue").insert(notification).execute()
    print("✅ Notification queued successfully")
except Exception as e:
    print(f"❌ Error queuing notification: {e}")

# Test 5: View pending content
print("\n5️⃣ Checking pending content view...")
try:
    pending = supabase.table("v_pending_content").select("*").execute()
    print(f"✅ Found {len(pending.data)} pending content items")
    if pending.data:
        print(json.dumps(pending.data[0], indent=2, default=str))
except Exception as e:
    print(f"❌ Error checking pending content: {e}")

print("\n✨ Testing complete! Your Supabase database is ready for the pipeline.")
print("\n🧹 Cleaning up test data...")

# Cleanup
try:
    supabase.table("notification_queue").delete().eq("talk_id", "TEST001").execute()
    supabase.table("social_content").delete().eq("talk_id", "TEST001").execute()
    supabase.table("talks").delete().eq("talk_id", "TEST001").execute()
    print("✅ Test data cleaned up")
except Exception as e:
    print(f"⚠️  Error cleaning up: {e}")

print("\n📝 Next steps:")
print("1. Set up n8n and import the workflow template")
print("2. Configure n8n with your Supabase credentials")
print("3. Add OpenAI API key for content generation")
print("4. Configure email settings for notifications")