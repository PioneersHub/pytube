#!/usr/bin/env python3
"""Quick test script to verify YouTube configuration."""

import json
import sys
from pathlib import Path

# Check config file
config_file = Path("config_local.yaml")
if not config_file.exists():
    print("✗ config_local.yaml not found")
    sys.exit(1)

import yaml

with open(config_file) as f:
    config = yaml.safe_load(f)

print("YouTube Configuration Test")
print("=" * 40)

# Check YouTube section
if "youtube" not in config:
    print("✗ No 'youtube' section in config")
    sys.exit(1)

yt = config["youtube"]

# Check client secrets
print("\n1. Client Secrets:")
client_secrets = yt.get("client_secrets_file", "NOT SET")
print(f"   File: {client_secrets}")
if client_secrets != "NOT SET":
    cs_path = Path(client_secrets)
    if cs_path.exists():
        print(f"   ✓ File exists ({cs_path.stat().st_size} bytes)")
    else:
        print(f"   ✗ File NOT FOUND")

# Check API key
print("\n2. API Key:")
api_key = yt.get("api_key", "")
if api_key:
    print(f"   ✓ API key is set (length: {len(api_key)})")
else:
    print(f"   ✗ API key NOT SET")

# Check channels
print("\n3. Channels:")
channels = yt.get("channels", {})
if not channels:
    print("   ✗ No channels configured")
else:
    for name, ch in channels.items():
        print(f"\n   {name}:")
        print(f"     Channel ID: {ch.get('id', 'NOT SET')}")
        print(f"     Playlist ID: {ch.get('playlist_id', 'NOT SET')}")

# Check token
print("\n4. OAuth Token:")
token_path = yt.get("token_path", "token.json")
print(f"   Path: {token_path}")
if Path(token_path).exists():
    print(f"   ✓ Token file exists")
    # Check if expired
    try:
        with open(token_path) as f:
            token_data = json.load(f)
        if "expiry" in token_data:
            print(f"   Expiry: {token_data['expiry']}")
    except:
        pass
else:
    print(f"   ⚠️  Token file does not exist (will need to authenticate)")

print("\n" + "=" * 40)
print("Configuration check complete")
