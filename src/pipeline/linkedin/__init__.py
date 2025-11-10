"""LinkedIn posting pipeline for conference videos.

This module integrates with the influent library to post conference video releases
to LinkedIn. It reads release records, formats them for LinkedIn, creates influent
YAML files, and optionally publishes them via the influent CLI.

Workflow:
    1. Release records are generated with AI summaries (text_generation module)
    2. prepare_posts.py reads release records and creates influent YAML files
    3. publish_posts.py executes influent CLI to post to LinkedIn

Usage:
    # Prepare LinkedIn posts from release records
    python -m src.pipeline.linkedin.prepare_posts --all

    # Publish prepared posts via influent
    python -m src.pipeline.linkedin.publish_posts --all
"""

from .models import LinkedInPost, LinkedInPostMetadata

__all__ = ["LinkedInPost", "LinkedInPostMetadata"]
