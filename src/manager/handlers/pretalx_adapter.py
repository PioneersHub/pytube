"""
Adapter to handle different Pretalx API response formats.

This module provides functions to handle both expanded and reference-based
Pretalx API responses, ensuring compatibility with pytanis models.
"""

import contextlib
import json
from typing import Any

import httpx
from httpx import QueryParams
from pytanis import PretalxClient

from manager import conf, logger


def fetch_and_expand_submissions(
    client: PretalxClient, event_slug: str, params: QueryParams | None = None
) -> tuple[int, list[dict[str, Any]]]:
    """
    Fetch submissions from Pretalx API and expand references if needed.

    The Pretalx API may return references (IDs) instead of full objects for
    related fields. This function detects and expands those references.

    Args:
        client: PretalxClient instance
        event_slug: Event identifier
        params: Query parameters for the API call

    Returns:
        Tuple of (count, list of expanded submission dictionaries)
    """
    # First, try to get the raw response data
    # We'll need to patch into the client's internals

    # Build the URL - use default Pretalx URL
    base_url = "https://pretalx.com"
    if hasattr(client, "_config") and client._config:
        with contextlib.suppress(AttributeError):
            base_url = client._config.pretalx_base_url.rstrip("/")

    url = f"{base_url}/api/events/{event_slug}/submissions/"

    # Get authentication headers if available
    headers = {}
    if hasattr(client, "_config") and client._config:
        try:
            if hasattr(client._config, "pretalx_token") and client._config.pretalx_token:
                headers["Authorization"] = f"Token {client._config.pretalx_token}"
        except AttributeError:
            pass

    # Make the request with pagination support
    all_results = []
    next_url = url
    total_count = 0

    with httpx.Client() as http_client:
        while next_url:
            if next_url != url:
                # For pagination, use the full next URL
                response = http_client.get(next_url, headers=headers)
            else:
                # First request with params
                response = http_client.get(next_url, params=params, headers=headers)

            response.raise_for_status()
            data = response.json()

            results = data.get("results", [])
            total_count = data.get("count", len(results))
            all_results.extend(results)

            # Check for next page
            next_url = data.get("next")
            if next_url and not next_url.startswith("http"):
                # Make it absolute if relative
                next_url = base_url + next_url

    # Check if we need to expand references
    if all_results and _needs_expansion(all_results[0]):
        logger.info("Detected reference-based API response, expanding references...")
        expanded_results = []

        for item in all_results:
            expanded_item = _expand_submission(client, event_slug, item)
            expanded_results.append(expanded_item)

        return total_count, expanded_results

    return total_count, all_results


def _needs_expansion(submission_data: dict[str, Any]) -> bool:
    """
    Check if a submission response needs reference expansion.

    Args:
        submission_data: Raw submission data from API

    Returns:
        True if references need to be expanded
    """
    # Check if speakers is a list of strings (IDs) instead of objects
    speakers = submission_data.get("speakers", [])
    if speakers and isinstance(speakers[0], str):
        return True

    # Check if submission_type is an ID instead of object
    if isinstance(submission_data.get("submission_type"), int):
        return True

    # Check if required fields are missing
    required_fields = ["submission_type_id", "is_featured"]
    is_missing = any(field not in submission_data for field in required_fields)
    return is_missing


def _fetch_speaker_minimal(client: PretalxClient, event_slug: str, speaker_id: str) -> dict[str, Any]:
    """
    Fetch minimal speaker data without answers to avoid validation issues.

    Args:
        client: PretalxClient instance
        event_slug: Event identifier
        speaker_id: Speaker code/ID

    Returns:
        Minimal speaker data dictionary
    """
    import httpx

    # Build the URL
    base_url = "https://pretalx.com"
    if hasattr(client, "_config") and client._config:
        with contextlib.suppress(AttributeError):
            base_url = client._config.pretalx_base_url.rstrip("/")

    url = f"{base_url}/api/events/{event_slug}/speakers/{speaker_id}/"

    # Get authentication headers if available
    headers = {}
    if hasattr(client, "_config") and client._config:
        try:
            if hasattr(client._config, "pretalx_token") and client._config.pretalx_token:
                headers["Authorization"] = f"Token {client._config.pretalx_token}"
        except AttributeError:
            pass

    # Make the request
    with httpx.Client() as http_client:
        response = http_client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

    # Return only the essential fields
    return {
        "code": data.get("code", speaker_id),
        "name": data.get("name", "Unknown Speaker"),
        "biography": data.get("biography"),
        "avatar": data.get("avatar"),
        "email": data.get("email"),
    }


def _expand_submission(client: PretalxClient, event_slug: str, submission_data: dict[str, Any]) -> dict[str, Any]:
    """
    Expand references in a submission to full objects.

    Args:
        client: PretalxClient instance
        event_slug: Event identifier
        submission_data: Raw submission data with references

    Returns:
        Expanded submission data
    """
    expanded = submission_data.copy()

    # Expand speakers if they are references
    if "speakers" in expanded and expanded["speakers"] and isinstance(expanded["speakers"][0], str):
        expanded_speakers = []
        for speaker_id in expanded["speakers"]:
            try:
                # Fetch speaker without expanded answers to avoid validation issues
                speaker_data = _fetch_speaker_minimal(client, event_slug, speaker_id)
                expanded_speakers.append(speaker_data)
            except Exception as e:
                logger.warning(f"Failed to expand speaker {speaker_id}: {e}")
                # Fallback to minimal speaker data
                expanded_speakers.append(
                    {
                        "code": speaker_id,
                        "name": "Unknown Speaker",
                        "biography": None,
                        "avatar": None,
                        "email": None,
                    }
                )
        expanded["speakers"] = expanded_speakers

    # Handle submission_type - convert ID to object if needed
    if isinstance(expanded.get("submission_type"), int):
        # Store the ID and create a default object
        expanded["submission_type_id"] = expanded["submission_type"]
        expanded["submission_type"] = {
            "en": "Talk",  # Default value
            "de": None,
        }

    # Handle track - convert ID to object if needed
    if isinstance(expanded.get("track"), int):
        # Store the ID and create a default object
        expanded["track_id"] = expanded["track"]
        expanded["track"] = {
            "en": "General",  # Default value
            "de": None,
        }

    # Add missing required fields with defaults
    if "submission_type_id" not in expanded:
        expanded["submission_type_id"] = 0  # Default ID

    if "is_featured" not in expanded:
        expanded["is_featured"] = False  # Default value

    # Expand answers if they are references
    if "answers" in expanded and expanded["answers"] and isinstance(expanded["answers"][0], int):
        # For now, we'll remove answer references as they're optional
        expanded["answers"] = []

    # Handle resources if they are references
    if "resources" in expanded and expanded["resources"] and isinstance(expanded["resources"][0], int):
        expanded["resources"] = []  # Empty list as default

    return expanded


def _get_event_dir() -> Path:
    """Get the event-specific directory for data storage."""
    from pathlib import Path

    event_slug = conf.pretalx.event_slug
    if not event_slug or event_slug == "pretalx-uri-slug":
        # Fallback to default structure for backward compatibility
        return Path(conf.dirs.work_dir)
    return Path(conf.dirs.work_dir) / event_slug


def load_submission_from_cache(code: str) -> dict[str, Any] | None:
    """
    Load a submission from the cached JSON files.

    Args:
        code: Submission code

    Returns:
        Submission data or None if not found
    """
    event_dir = _get_event_dir()
    cache_file = event_dir / "pretalx" / f"{code}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    return None


def fetch_and_expand_speakers(
    client: PretalxClient, event_slug: str, params: QueryParams | None = None
) -> tuple[int, list[dict[str, Any]]]:
    """
    Fetch speakers from Pretalx API and expand references if needed.

    Args:
        client: PretalxClient instance
        event_slug: Event identifier
        params: Query parameters for the API call

    Returns:
        Tuple of (count, list of expanded speaker dictionaries)
    """
    import httpx

    # Build the URL
    base_url = "https://pretalx.com"
    if hasattr(client, "_config") and client._config:
        with contextlib.suppress(AttributeError):
            base_url = client._config.pretalx_base_url.rstrip("/")

    url = f"{base_url}/api/events/{event_slug}/speakers/"

    # Get authentication headers if available
    headers = {}
    if hasattr(client, "_config") and client._config:
        try:
            if hasattr(client._config, "pretalx_token") and client._config.pretalx_token:
                headers["Authorization"] = f"Token {client._config.pretalx_token}"
        except AttributeError:
            pass

    # Make the request with pagination support
    all_results = []
    next_url = url
    total_count = 0

    with httpx.Client() as http_client:
        while next_url:
            if next_url != url:
                # For pagination, use the full next URL
                response = http_client.get(next_url, headers=headers)
            else:
                # First request with params
                response = http_client.get(next_url, params=params, headers=headers)

            response.raise_for_status()
            data = response.json()

            results = data.get("results", [])
            total_count = data.get("count", len(results))

            # Process speakers to ensure they don't have reference-based answers
            for speaker_data in results:
                # If answers are references (IDs), remove them
                if (
                    "answers" in speaker_data
                    and speaker_data["answers"]
                    and isinstance(speaker_data["answers"][0], int)
                ):
                    speaker_data = speaker_data.copy()
                    speaker_data["answers"] = []  # Empty list to avoid validation issues

                # If submissions are references, we can leave them as is since they're just strings
                all_results.append(speaker_data)

            # Check for next page
            next_url = data.get("next")
            if next_url and not next_url.startswith("http"):
                # Make it absolute if relative
                next_url = base_url + next_url

    return total_count, all_results


def save_submission_to_cache(submission_data: dict[str, Any]) -> None:
    """
    Save a submission to the cache directory.

    Args:
        submission_data: Submission data to save
    """
    event_dir = _get_event_dir()
    cache_dir = event_dir / "pretalx"
    cache_dir.mkdir(parents=True, exist_ok=True)

    code = submission_data.get("code")
    if code:
        cache_file = cache_dir / f"{code}.json"
        cache_file.write_text(json.dumps(submission_data, indent=4))


def save_speaker_to_cache(speaker_data: dict[str, Any]) -> None:
    """
    Save a speaker to the cache directory.

    Args:
        speaker_data: Speaker data to save
    """
    event_dir = _get_event_dir()
    cache_dir = event_dir / "pretalx_speakers"
    cache_dir.mkdir(parents=True, exist_ok=True)

    code = speaker_data.get("code")
    if code:
        cache_file = cache_dir / f"{code}.json"
        cache_file.write_text(json.dumps(speaker_data, indent=4))
