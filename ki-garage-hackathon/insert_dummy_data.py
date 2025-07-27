#!/usr/bin/env python3
"""
Insert dummy data into Supabase for testing the pipeline
"""

import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client, Client
import random

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_API_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

print("🎯 Inserting dummy data into Supabase...\n")

# Sample talk data
dummy_talks = [
    {
        "talk_id": "DUMMY01",
        "title": "Building Scalable Python Applications with AsyncIO",
        "talk_date": (datetime.now() - timedelta(days=5)).isoformat(),
        "youtube_url": "https://youtube.com/watch?v=dummy1",
        "processing_status": "new"
    },
    {
        "talk_id": "DUMMY02",
        "title": "Machine Learning in Production: Best Practices",
        "talk_date": (datetime.now() - timedelta(days=3)).isoformat(),
        "youtube_url": "https://youtube.com/watch?v=dummy2",
        "processing_status": "new"
    },
    {
        "talk_id": "DUMMY03",
        "title": "Data Visualization with Python: Beyond Matplotlib",
        "talk_date": (datetime.now() - timedelta(days=1)).isoformat(),
        "youtube_url": None,  # Not yet uploaded
        "processing_status": "new"
    }
]

# Insert talks
print("1️⃣ Inserting talks...")
for talk in dummy_talks:
    try:
        result = supabase.table("talks").insert(talk).execute()
        print(f"✅ Inserted: {talk['title']}")
    except Exception as e:
        if "duplicate key" in str(e):
            print(f"⚠️  Talk {talk['talk_id']} already exists")
        else:
            print(f"❌ Error: {e}")

# Sample social content for first talk
print("\n2️⃣ Inserting sample social content...")
social_content_samples = [
    {
        "talk_id": "DUMMY01",
        "platform": "youtube",
        "content_type": "description",
        "generated_content": """Building Scalable Python Applications with AsyncIO

Speaker(s): Dr. Jane Smith

Description:
Dive deep into Python's AsyncIO library and learn how to build highly scalable applications. This talk covers advanced patterns, best practices, and real-world examples.

Key Topics:
• AsyncIO fundamentals and event loops
• Concurrent programming patterns
• Performance optimization techniques
• Real-world case studies

Conference: PyCon DE & PyData 2025
Track: Advanced Python

#python #asyncio #scalability #pycon2025""",
        "status": "generated",
        "owner_email": os.getenv("SOCIAL_MEDIA_OWNER_EMAIL", "social-media@pycon.example")
    },
    {
        "talk_id": "DUMMY01",
        "platform": "linkedin",
        "content_type": "post",
        "generated_content": """🚀 Just watched an incredible talk on AsyncIO at #PyConDE2025!

Dr. Jane Smith demonstrated how to build scalable Python applications using AsyncIO, covering everything from event loops to real-world performance optimization.

Key takeaways:
✅ AsyncIO can handle thousands of concurrent connections
✅ Proper error handling is crucial for production systems
✅ Context managers simplify resource management

Watch the full talk: https://youtube.com/watch?v=dummy1

#python #asyncprogramming #softwareengineering #pydata""",
        "status": "reviewed",
        "owner_email": os.getenv("SOCIAL_MEDIA_OWNER_EMAIL", "social-media@pycon.example")
    },
    {
        "talk_id": "DUMMY02",
        "platform": "youtube",
        "content_type": "description",
        "generated_content": "This content is still being generated...",
        "status": "pending",
        "owner_email": os.getenv("SOCIAL_MEDIA_OWNER_EMAIL", "social-media@pycon.example")
    }
]

for content in social_content_samples:
    try:
        result = supabase.table("social_content").insert(content).execute()
        print(f"✅ Inserted {content['platform']} content for {content['talk_id']}")
    except Exception as e:
        print(f"❌ Error: {e}")

# Sample notifications
print("\n3️⃣ Inserting sample notifications...")
notifications = [
    {
        "talk_id": "DUMMY01",
        "recipient_type": "social_media_owner",
        "recipient_email": os.getenv("SOCIAL_MEDIA_OWNER_EMAIL", "social-media@pycon.example"),
        "notification_type": "content_ready_for_review",
        "sent": False
    },
    {
        "talk_id": "DUMMY02",
        "recipient_type": "speaker",
        "recipient_email": "speaker@example.com",
        "notification_type": "content_ready_for_review",
        "sent": True,
        "sent_at": datetime.now().isoformat()
    }
]

for notification in notifications:
    try:
        result = supabase.table("notification_queue").insert(notification).execute()
        print(f"✅ Queued notification for {notification['talk_id']}")
    except Exception as e:
        print(f"❌ Error: {e}")

# Show summary
print("\n📊 Summary of data in database:")
try:
    talks_count = len(supabase.table("talks").select("*").execute().data)
    content_count = len(supabase.table("social_content").select("*").execute().data)
    notifications_count = len(supabase.table("notification_queue").select("*").execute().data)
    
    print(f"- Talks: {talks_count}")
    print(f"- Social content: {content_count}")
    print(f"- Notifications: {notifications_count}")
    
    # Show pending content
    pending = supabase.table("v_pending_content").select("*").execute()
    print(f"\n📝 Pending content for review: {len(pending.data)} items")
    
except Exception as e:
    print(f"Error getting summary: {e}")

print("\n✨ Done! Your database now has sample data for testing.")
print("\n💡 Next: Run the n8n workflow to see how it processes this data!")