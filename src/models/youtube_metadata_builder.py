"""Builder for creating YouTube metadata from conference session data.

This module provides functionality to transform SessionRecord data into
YouTube-compatible metadata, including template rendering and validation.
"""
raise Exception("Do not use this module")

from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, Template



from src.models.youtube_metadata import (
    YouTubeMetadataDefaults,
    YouTubeRecordingDetails,
    YouTubeSnippet,
    YouTubeStatus,
    YouTubeVideoMetadata,
)


class YouTubeMetadataBuilder:
    """Builds YouTube metadata from conference session records.

    This class handles the transformation of conference session data
    into YouTube-compatible metadata, including:
    - Title optimization for YouTube's 100 character limit
    - Description rendering using Jinja2 templates
    - Tag generation from session data
    - Privacy and scheduling settings
    """

    def __init__(
        self,
        template_path: Path | str | None = None,
        template_string: str | None = None,
        defaults: YouTubeMetadataDefaults | None = None,
        conference_name: str = "PyCon DE & PyData 2025",
    ):
        """Initialize the metadata builder.

        Args:
            template_path: Path to Jinja2 template file
            template_string: Template string (if not using file)
            defaults: Default values for metadata fields
            conference_name: Conference name for title optimization
        """
        self.conference_name = conference_name
        self.defaults = defaults or YouTubeMetadataDefaults()

        # Initialize template
        if template_path:
            template_dir = Path(template_path).parent
            template_name = Path(template_path).name
            env = Environment(
                loader=FileSystemLoader(str(template_dir)),
                autoescape=False,  # YouTube doesn't need HTML escaping
            )
            self.template = env.get_template(template_name)
        elif template_string:
            self.template = Template(template_string)
        else:
            # Default minimal template
            self.template = Template(
                "{{ description }}\n\nSpeaker(s): {{ speakers }}\n\nRecorded at {{ conference_name }}, {{ date }}"
            )

    def build_metadata(
        self,
        session_record: dict[str, Any],
        video_id: str,
        channel: str,
        pretalx_youtube_map: dict[str, str] | None = None,
    ) -> YouTubeVideoMetadata:
        """Build YouTube metadata from a session record.

        Args:
            session_record: Session data dictionary
            video_id: YouTube video ID
            channel: Target YouTube channel
            pretalx_youtube_map: Optional mapping of Pretalx IDs to YouTube IDs

        Returns:
            Complete YouTube metadata object
        """
        # Extract pretalx_id
        pretalx_id = session_record.get("pretalx_id", "")

        # Build snippet
        snippet = self._build_snippet(session_record)

        # Build status
        status = self._build_status(session_record)

        # Build recording details
        recording_details = self._build_recording_details(session_record)

        # Create metadata object
        metadata = YouTubeVideoMetadata(
            video_id=video_id,
            pretalx_id=pretalx_id,
            channel=channel,
            snippet=snippet,
            status=status,
            recording_details=recording_details,
        )

        return metadata

    def _build_snippet(self, session_record: dict[str, Any]) -> YouTubeSnippet:
        """Build YouTube snippet from session data."""
        # Get title and optimize for YouTube
        title = session_record.get("title", "")
        youtube_title = self._optimize_title(title)

        # Render description
        description = self._render_description(session_record)

        # Generate tags
        tags = self._generate_tags(session_record)

        snippet = YouTubeSnippet(
            title=youtube_title,
            description=description,
            tags=tags,
            category_id=self.defaults.category_id,
            default_language=self.defaults.default_language,
        )

        return snippet

    def _build_status(self, session_record: dict[str, Any]) -> YouTubeStatus:
        """Build YouTube status from session data."""
        status = YouTubeStatus(
            privacy_status=self.defaults.privacy_status,
            embeddable=self.defaults.embeddable,
            license=self.defaults.license,
        )

        # Check if there's a scheduled publish date
        publish_at = session_record.get("youtube_publish_at")
        if publish_at:
            if isinstance(publish_at, str):
                publish_at = datetime.fromisoformat(publish_at.replace("Z", "+00:00"))
            status.publish_at = publish_at
            status.privacy_status = "private"  # Required for scheduled publishing

        return status

    def _build_recording_details(self, session_record: dict[str, Any]) -> YouTubeRecordingDetails | None:
        """Build recording details from session data."""
        # Try different date fields
        recorded_date = None

        # Check for recorded_date first
        if "recorded_date" in session_record:
            recorded_date = session_record["recorded_date"]
        # Fall back to session slot start time
        elif "pretalx_session" in session_record:
            pretalx_data = session_record["pretalx_session"]
            if isinstance(pretalx_data, dict) and "session" in pretalx_data:
                session_data = pretalx_data["session"]
                if isinstance(session_data, dict) and "slot" in session_data:
                    slot_data = session_data["slot"]
                    if isinstance(slot_data, dict) and "start" in slot_data:
                        recorded_date = slot_data["start"]

        if recorded_date:
            return YouTubeRecordingDetails(recording_date=recorded_date)

        return None

    def _optimize_title(self, title: str) -> str:
        """Optimize title for YouTube's 100 character limit.

        Strategy:
        1. Remove restricted characters (< >)
        2. If title fits, add conference name in brackets
        3. If too long, truncate with ellipsis
        """
        # Remove restricted characters
        clean_title = title.replace("<", "").replace(">", "").strip()

        # YouTube max length
        max_length = 100

        # If title is already too long, truncate it
        if len(clean_title) > max_length:
            return f"{clean_title[: max_length - 1]}…"

        # Try to add conference name
        full_title = f"{clean_title} [{self.conference_name}]"
        if len(full_title) <= max_length:
            return full_title

        # Just return clean title if adding conference name makes it too long
        return clean_title

    def _render_description(self, session_record: dict[str, Any]) -> str:
        """Render description using Jinja2 template."""
        # Prepare template context
        context = self._prepare_template_context(session_record)

        # Render template
        description = self.template.render(**context)

        # Clean up description
        description = description.replace("<", "").replace(">", "")

        # Ensure it fits YouTube's limit
        max_length = 5000
        if len(description) > max_length:
            # Try with shorter description
            if "sm_short_text" in session_record:
                context["description"] = session_record["sm_short_text"]
                description = self.template.render(**context)

            # If still too long, truncate
            if len(description) > max_length:
                description = description[: max_length - 3] + "..."

        return description

    def _prepare_template_context(self, session_record: dict[str, Any]) -> dict[str, Any]:
        """Prepare context for template rendering."""
        # Extract speaker names
        speakers = []
        if "speakers" in session_record:
            for speaker in session_record["speakers"]:
                if isinstance(speaker, dict) and "name" in speaker:
                    speakers.append(speaker["name"])
                elif isinstance(speaker, str):
                    speakers.append(speaker)

        # Get description text (prefer sm_long_text for YouTube)
        description = (
            session_record.get("sm_long_text")
            or session_record.get("description")
            or session_record.get("abstract")
            or ""
        )

        # Get teaser text
        teaser_text = session_record.get("sm_teaser_text") or session_record.get("abstract", "")[:200]

        # Get date
        date_str = "2025"  # Default
        if "recorded_date" in session_record:
            try:
                if isinstance(session_record["recorded_date"], str):
                    recorded_date = datetime.fromisoformat(session_record["recorded_date"].replace("Z", "+00:00"))
                else:
                    recorded_date = session_record["recorded_date"]
                date_str = recorded_date.strftime("%d.%m.%Y")
            except (ValueError, AttributeError):
                pass

        # Build session link
        pretalx_id = session_record.get("pretalx_id", "")
        session_link = f"https://2025.pycon.de/program/{pretalx_id}/"

        context = {
            "description": description,
            "speakers": ", ".join(speakers),
            "teaser_text": teaser_text,
            "date": date_str,
            "session_link": session_link,
            "conference_name": self.conference_name,
            "pydata": "pydata" in session_record.get("youtube_channel", "").lower(),
        }

        return context

    def _generate_tags(self, session_record: dict[str, Any]) -> list[str]:
        """Generate tags from session data.

        Combines:
        - Base tags from defaults
        - Track name
        - Speaker names
        - Keywords from title/abstract
        """
        tags = list(self.defaults.tags_base)  # Copy base tags

        # Add track if available
        if "track" in session_record:
            track = session_record["track"]
            if isinstance(track, dict) and "name" in track:
                tags.append(track["name"])
            elif isinstance(track, str):
                tags.append(track)

        # Add speaker names
        if "speakers" in session_record:
            for speaker in session_record["speakers"]:
                if isinstance(speaker, dict) and "name" in speaker:
                    tags.append(speaker["name"])

        # Extract keywords from title
        title = session_record.get("title", "")
        title_words = title.split()

        # Add significant words from title (> 4 chars, not common words)
        common_words = {"with", "from", "this", "that", "have", "been", "will", "your"}
        for word in title_words:
            clean_word = word.strip(".,!?:;\"'")
            if len(clean_word) > 4 and clean_word.lower() not in common_words:
                tags.append(clean_word)

        # Limit total tags and remove duplicates
        # YouTube allows up to 500 tags, but 20-30 is recommended
        unique_tags = []
        seen = set()
        for tag in tags[:30]:  # Limit to 30 tags
            tag_lower = tag.lower()
            if tag_lower not in seen:
                seen.add(tag_lower)
                unique_tags.append(tag)

        return unique_tags
