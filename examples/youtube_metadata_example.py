"""Example usage of YouTube metadata models for conference videos.

This script demonstrates how to:
1. Load session data from JSON
2. Build YouTube metadata
3. Create update requests
4. Handle batch updates
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.models.youtube_metadata import (
    YouTubeVideoMetadata,
    YouTubeMetadataDefaults
)
from src.models.youtube_metadata_builder import YouTubeMetadataBuilder


def example_single_video():
    """Example: Process a single video."""
    print("=== Single Video Example ===\n")
    
    # Sample session data (would come from SessionRecord)
    session_data = {
        "pretalx_id": "ABC123",
        "title": "Building Scalable Python Applications with Async/Await",
        "abstract": "Learn how to build high-performance Python applications",
        "description": "This comprehensive talk covers async programming...",
        "sm_long_text": """
        In this session, we'll explore Python's async/await capabilities
        and how they can be used to build scalable applications.
        
        Topics covered:
        - Understanding the event loop
        - Writing async functions
        - Managing concurrent tasks
        - Best practices and common pitfalls
        """,
        "sm_teaser_text": "Master Python async programming!",
        "speakers": [
            {"name": "Dr. Jane Smith", "biography": "Python core developer"},
            {"name": "Alex Johnson", "biography": "Senior engineer at TechCorp"}
        ],
        "track": {"name": "Advanced Python"},
        "recorded_date": "2025-04-15T10:30:00+00:00"
    }
    
    # Initialize builder with custom template
    template = Path("src/manager/templates/youtube_2025.txt")
    builder = YouTubeMetadataBuilder(
        template_path=template if template.exists() else None,
        conference_name="PyCon DE & PyData 2025"
    )
    
    # Build metadata
    metadata = builder.build_metadata(
        session_record=session_data,
        video_id="dQw4w9WgXcQ",  # Example YouTube ID
        channel="pycon"
    )
    
    # Print the generated metadata
    print(f"Video ID: {metadata.video_id}")
    print(f"Pretalx ID: {metadata.pretalx_id}")
    print(f"Channel: {metadata.channel}")
    print(f"\nTitle: {metadata.snippet.title}")
    print(f"Title length: {len(metadata.snippet.title)}/100")
    print(f"\nDescription preview (first 200 chars):")
    print(metadata.snippet.description[:200] + "...")
    print(f"\nTags ({len(metadata.snippet.tags)}): {', '.join(metadata.snippet.tags[:10])}...")
    
    # Create update request
    update_request = metadata.create_update_request()
    print(f"\nUpdate parts: {', '.join(update_request.update_parts)}")
    print(f"API request body:")
    print(json.dumps(update_request.to_api_dict(), indent=2, default=str))


def example_batch_processing():
    """Example: Process multiple videos with scheduling."""
    print("\n\n=== Batch Processing Example ===\n")
    
    # Sample data for multiple videos
    videos = [
        {
            "pretalx_id": "TALK01",
            "title": "Introduction to Machine Learning with Python",
            "video_id": "abc123",
            "channel": "pydata"
        },
        {
            "pretalx_id": "TALK02", 
            "title": "Web Development with Django",
            "video_id": "def456",
            "channel": "pycon"
        },
        {
            "pretalx_id": "TALK03",
            "title": "Data Visualization with Matplotlib",
            "video_id": "ghi789",
            "channel": "pydata"
        }
    ]
    
    # Initialize builder
    builder = YouTubeMetadataBuilder()
    
    # Process videos with scheduled publishing
    start_date = datetime.now(timezone.utc) + timedelta(days=7)
    publish_interval = timedelta(days=2)
    
    processed_metadata = []
    
    for i, video_data in enumerate(videos):
        # Calculate publish date
        publish_date = start_date + (publish_interval * i)
        
        # Add publish date to session data
        video_data["youtube_publish_at"] = publish_date.isoformat()
        
        # Build metadata
        metadata = builder.build_metadata(
            session_record=video_data,
            video_id=video_data["video_id"],
            channel=video_data["channel"]
        )
        
        processed_metadata.append(metadata)
        
        print(f"Video {i+1}: {video_data['title']}")
        print(f"  - Channel: {metadata.channel}")
        print(f"  - Privacy: {metadata.status.privacy_status}")
        print(f"  - Publish at: {metadata.status.publish_at}")
        print()


def example_validation_errors():
    """Example: Demonstrate validation and error handling."""
    print("\n=== Validation Examples ===\n")
    
    # Example 1: Title too long
    try:
        from src.models.youtube_metadata import YouTubeSnippet
        snippet = YouTubeSnippet(
            title="A" * 150  # Too long
        )
    except ValueError as e:
        print(f"Title validation error: {e}")
    
    # Example 2: Past publish date
    try:
        from src.models.youtube_metadata import YouTubeStatus
        past_date = datetime.now(timezone.utc) - timedelta(days=1)
        status = YouTubeStatus(
            publish_at=past_date
        )
    except ValueError as e:
        print(f"Publish date error: {e}")
    
    # Example 3: Restricted characters removed
    snippet = YouTubeSnippet(
        title="My <awesome> Talk",
        description="This is <great>"
    )
    print(f"\nRestricted chars removed:")
    print(f"  Title: '{snippet.title}'")
    print(f"  Description: '{snippet.description}'")


def example_custom_defaults():
    """Example: Using custom default values."""
    print("\n\n=== Custom Defaults Example ===\n")
    
    # Create custom defaults
    custom_defaults = YouTubeMetadataDefaults(
        category_id="27",  # Education instead of Science & Technology
        default_language="de",  # German
        privacy_status="private",  # Private by default
        tags_base=["Python", "Programmierung", "Konferenz", "2025"]
    )
    
    # Initialize builder with custom defaults
    builder = YouTubeMetadataBuilder(defaults=custom_defaults)
    
    # Build metadata
    metadata = builder.build_metadata(
        session_record={
            "pretalx_id": "GER001",
            "title": "Python für Anfänger",
            "description": "Eine Einführung in Python"
        },
        video_id="xyz789",
        channel="pycon"
    )
    
    print(f"Category ID: {metadata.snippet.category_id}")
    print(f"Language: {metadata.snippet.default_language}")
    print(f"Privacy: {metadata.status.privacy_status}")
    print(f"Base tags: {metadata.snippet.tags[:4]}")


def example_integration_with_youtube_api():
    """Example: Show how to integrate with actual YouTube API."""
    print("\n\n=== YouTube API Integration Example ===\n")
    
    print("To use with the actual YouTube API:\n")
    print("1. Build metadata using YouTubeMetadataBuilder")
    print("2. Create update request:")
    print("   request = metadata.create_update_request()")
    print("3. Call YouTube API:")
    print("   youtube.videos().update(")
    print("       part=','.join(request.update_parts),")
    print("       body=request.to_api_dict()")
    print("   ).execute()")
    
    # Show example API call structure
    metadata = YouTubeVideoMetadata(
        video_id="test123",
        pretalx_id="DEMO01",
        channel="pycon",
        snippet=YouTubeSnippet(
            title="Demo Video",
            description="This is a demo",
            tags=["Python", "Demo"]
        ),
        status=YouTubeStatus(
            privacy_status="unlisted"
        )
    )
    
    request = metadata.create_update_request()
    
    print(f"\nParts: {request.update_parts}")
    print("\nRequest body:")
    print(json.dumps(request.to_api_dict(), indent=2))


if __name__ == "__main__":
    # Run all examples
    example_single_video()
    example_batch_processing()
    example_validation_errors()
    example_custom_defaults()
    example_integration_with_youtube_api()