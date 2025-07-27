#!/usr/bin/env python3
"""
Reset talk status to 'new' for testing the pipeline
"""

import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_API_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

print("🔄 Resetting talk status for testing...\n")

try:
    # Reset dummy talks to 'new' status
    result = supabase.table("talks").update({
        "processing_status": "new"
    }).like("talk_id", "DUMMY%").execute()
    
    print(f"✅ Reset {len(result.data)} talks to 'new' status")
    
    # Show current talks
    talks = supabase.table("talks").select("talk_id, title, processing_status").execute()
    print("\n📊 Current talks in database:")
    for talk in talks.data:
        status_icon = "🆕" if talk['processing_status'] == 'new' else "✅"
        print(f"{status_icon} {talk['talk_id']}: {talk['title']} ({talk['processing_status']})")
        
except Exception as e:
    print(f"❌ Error: {e}")

print("\n💡 Talks are ready for processing in n8n!")