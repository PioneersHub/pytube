#!/usr/bin/env python3
"""
Simple Supabase connection test
Run this after adding your credentials to .env file
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

print("🚀 PyTube Pipeline - Supabase Connection Test\n")

# Check for required environment variables
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_API_KEY")

if not supabase_url or not supabase_key:
    print("❌ Supabase credentials not found in .env file!")
    print("\nPlease add the following to your .env file:")
    print("SUPABASE_URL=https://your-project.supabase.co")
    print("SUPABASE_API_KEY=your-api-key")
    print("\nYou can find these in your Supabase project settings:")
    print("1. Go to https://app.supabase.com/")
    print("2. Select your project (or create a new one)")
    print("3. Go to Settings > API")
    print("4. Copy the Project URL and anon/public API key")
    sys.exit(1)

print("✅ Found Supabase credentials in .env file")
print(f"   URL: {supabase_url}")
print(f"   Key: {'*' * 20} (hidden)\n")

try:
    from supabase import create_client, Client
    print("✅ Supabase package is installed")
except ImportError:
    print("❌ Supabase package not found. Please run: uv add supabase")
    sys.exit(1)

# Try to connect
try:
    supabase: Client = create_client(supabase_url, supabase_key)
    print("✅ Successfully created Supabase client!")
    
    # Try a simple query to test connection
    result = supabase.table("talks").select("*").limit(1).execute()
    print("✅ Successfully connected to Supabase and queried 'talks' table")
    
except Exception as e:
    print(f"❌ Failed to connect or query: {e}")
    print("\nPossible issues:")
    print("- Check if your Supabase project is active")
    print("- Verify the API key is correct")
    print("- Make sure you've run the SQL schema in Supabase")

print("\n📝 Next steps:")
print("1. If connection failed, fix the issues above")
print("2. Run the SQL schema in your Supabase SQL editor")
print("3. Import the n8n workflow template")
print("4. Configure n8n with your Supabase credentials")