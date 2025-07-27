#!/usr/bin/env python3
"""
Supabase Setup and Testing Script
This script helps you set up and test your Supabase connection
"""

import os
import sys
from datetime import datetime
from typing import Optional
import json

# Check if supabase package is installed
try:
    from supabase import create_client, Client
except ImportError:
    print("Supabase package not found. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "supabase"])
    from supabase import create_client, Client

def setup_supabase() -> Optional[Client]:
    """Initialize Supabase client with environment variables."""
    
    # Try to load from environment variables
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_API_KEY")
    
    if not supabase_url or not supabase_key:
        print("\n⚠️  Supabase credentials not found in environment variables.")
        print("\nPlease provide your Supabase credentials:")
        print("You can find these in your Supabase project settings.")
        print("1. Go to https://app.supabase.com/")
        print("2. Select your project")
        print("3. Go to Settings > API")
        print("4. Copy the Project URL and anon/public API key\n")
        
        supabase_url = input("Enter your Supabase Project URL: ").strip()
        supabase_key = input("Enter your Supabase API Key (anon/public): ").strip()
        
        # Save to .env file for future use
        save_to_env = input("\nSave to .env file? (y/n): ").lower() == 'y'
        if save_to_env:
            with open('.env', 'a') as f:
                f.write(f"\nSUPABASE_URL={supabase_url}")
                f.write(f"\nSUPABASE_API_KEY={supabase_key}")
            print("✅ Credentials saved to .env file")
    
    try:
        supabase: Client = create_client(supabase_url, supabase_key)
        print("✅ Successfully connected to Supabase!")
        return supabase
    except Exception as e:
        print(f"❌ Failed to connect to Supabase: {e}")
        return None

def test_database_setup(supabase: Client):
    """Test if the database tables are properly set up."""
    print("\n🔍 Testing database setup...")
    
    tables_to_check = ['talks', 'social_content', 'notification_queue', 'speakers']
    
    for table in tables_to_check:
        try:
            # Try to query the table
            result = supabase.table(table).select("*").limit(1).execute()
            print(f"✅ Table '{table}' exists and is accessible")
        except Exception as e:
            print(f"❌ Table '{table}' not found or not accessible: {e}")
            print(f"   Please run the SQL schema in your Supabase SQL editor")

def insert_test_data(supabase: Client):
    """Insert test data to verify everything works."""
    print("\n📝 Inserting test data...")
    
    try:
        # Insert a test talk
        test_talk = {
            "talk_id": "TEST001",
            "title": "Test Talk: Introduction to Pipeline Automation",
            "talk_date": datetime.now().isoformat(),
            "processing_status": "new"
        }
        
        result = supabase.table("talks").insert(test_talk).execute()
        print("✅ Test talk inserted successfully")
        
        # Insert test social content
        test_content = {
            "talk_id": "TEST001",
            "platform": "youtube",
            "content_type": "description",
            "generated_content": "This is a test YouTube description for the pipeline test.",
            "status": "generated",
            "owner_email": "test@example.com"
        }
        
        result = supabase.table("social_content").insert(test_content).execute()
        print("✅ Test social content inserted successfully")
        
        # Query the data back
        talks = supabase.table("talks").select("*").eq("talk_id", "TEST001").execute()
        print(f"\n📊 Test data retrieved:")
        print(json.dumps(talks.data, indent=2))
        
    except Exception as e:
        print(f"❌ Error inserting test data: {e}")

def cleanup_test_data(supabase: Client):
    """Remove test data."""
    print("\n🧹 Cleaning up test data...")
    
    try:
        # Delete test social content first (due to foreign key)
        supabase.table("social_content").delete().eq("talk_id", "TEST001").execute()
        # Delete test talk
        supabase.table("talks").delete().eq("talk_id", "TEST001").execute()
        print("✅ Test data cleaned up successfully")
    except Exception as e:
        print(f"⚠️  Error cleaning up test data: {e}")

def main():
    print("🚀 PyTube Pipeline - Supabase Setup\n")
    
    # Setup Supabase connection
    supabase = setup_supabase()
    if not supabase:
        return
    
    # Test database setup
    test_database_setup(supabase)
    
    # Ask if user wants to insert test data
    if input("\n🤔 Would you like to insert and test with sample data? (y/n): ").lower() == 'y':
        insert_test_data(supabase)
        
        if input("\n🧹 Clean up test data? (y/n): ").lower() == 'y':
            cleanup_test_data(supabase)
    
    print("\n✨ Setup complete! Your Supabase connection is ready for n8n.")
    print("\n📝 Next steps:")
    print("1. Copy the SQL from 'supabase_schema.sql' to your Supabase SQL editor")
    print("2. Execute the SQL to create all tables")
    print("3. Use the credentials in your n8n workflow")
    print("\n🔑 n8n Configuration:")
    print(f"   SUPABASE_URL: {os.getenv('SUPABASE_URL', 'Check your .env file')}")
    print(f"   SUPABASE_API_KEY: {'*' * 20} (hidden)")

if __name__ == "__main__":
    main()