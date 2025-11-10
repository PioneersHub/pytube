"""Publish LinkedIn posts via influent CLI.

This script executes the influent CLI to publish prepared LinkedIn posts.
It processes YAML files in the posts/ directory and tracks publication status.

Usage:
    # Publish all prepared posts
    python -m src.pipeline.linkedin.publish_posts --all

    # Publish specific posts
    python -m src.pipeline.linkedin.publish_posts LRUKZQ.yaml 3CYZUH.yaml

    # Dry run (validate without posting)
    python -m src.pipeline.linkedin.publish_posts --all --dry-run

    # Limit number of posts
    python -m src.pipeline.linkedin.publish_posts --all --limit 5
"""

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import structlog

from pipeline.config import load_config
from pipeline.logger import setup_logging
from pipeline.paths import WorkPaths

from .models import LinkedInPostMetadata

logger = structlog.get_logger()


class LinkedInPublisher:
    """Publish LinkedIn posts via influent CLI."""

    def __init__(self):
        """Initialize the publisher."""
        self.config = load_config()
        self.paths = WorkPaths(self.config)

        # LinkedIn configuration
        try:
            self.linkedin_config = self.config.linkedin
        except AttributeError as e:
            raise ValueError("linkedin configuration not found in config") from e

        try:
            self.organization_name = self.linkedin_config.organization_name
        except AttributeError as e:
            raise ValueError("linkedin.organization_name not configured") from e

        # Setup directories
        self.linkedin_dir = self._get_linkedin_dir()
        self.posts_dir = self.linkedin_dir / "posts"
        self.metadata_dir = self.linkedin_dir / "metadata"
        self.published_dir = self.linkedin_dir / "published"

        # Create published directory
        self.published_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "linkedin_publisher_initialized",
            linkedin_dir=str(self.linkedin_dir),
            organization=self.organization_name,
        )

    def _get_linkedin_dir(self) -> Path:
        """Get LinkedIn posts directory from config or default.

        Returns:
            Path to LinkedIn posts directory
        """
        try:
            influent_path = self.linkedin_config.influent_path
        except AttributeError:
            influent_path = ""

        if influent_path:
            return Path(influent_path)

        # Default: {work_dir}/{event}/linkedin_posts/
        return self.paths.event_dir / "linkedin_posts"

    def publish_post(self, yaml_file: Path, dry_run: bool = False) -> bool:
        """Publish a single LinkedIn post via influent CLI.

        Args:
            yaml_file: Path to YAML file to publish
            dry_run: If True, validate without posting

        Returns:
            True if successful, False otherwise
        """
        if not yaml_file.exists():
            logger.error("yaml_file_not_found", file=str(yaml_file))
            return False

        pretalx_id = yaml_file.stem
        logger.info("publishing_post", pretalx_id=pretalx_id, dry_run=dry_run)

        # Build influent command
        cmd = [
            "influent",
            "--organization",
            self.organization_name,
            "post",
            yaml_file.name,
        ]

        if dry_run:
            cmd.insert(1, "--dry-run")

        try:
            # Run influent from posts directory
            result = subprocess.run(
                cmd,
                cwd=self.posts_dir,
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
            )

            logger.info("post_published", pretalx_id=pretalx_id, output=result.stdout)

            if not dry_run:
                # Update metadata
                self._update_metadata(pretalx_id, published=True)

                # Move to published directory
                published_file = self.published_dir / yaml_file.name
                yaml_file.rename(published_file)

                logger.info("post_moved_to_published", pretalx_id=pretalx_id)

            return True

        except subprocess.CalledProcessError as e:
            logger.error(
                "influent_command_failed",
                pretalx_id=pretalx_id,
                returncode=e.returncode,
                stdout=e.stdout,
                stderr=e.stderr,
            )
            return False

        except subprocess.TimeoutExpired:
            logger.error("influent_command_timeout", pretalx_id=pretalx_id)
            return False

        except Exception as e:
            logger.error("unexpected_error", pretalx_id=pretalx_id, error=str(e))
            return False

    def _update_metadata(self, pretalx_id: str, published: bool):
        """Update metadata with publication status.

        Args:
            pretalx_id: Pretalx session ID
            published: Publication status
        """
        metadata_file = self.metadata_dir / f"{pretalx_id}.json"

        if not metadata_file.exists():
            logger.warning("metadata_file_not_found", pretalx_id=pretalx_id)
            return

        try:
            with metadata_file.open() as f:
                metadata_dict = json.load(f)

            metadata = LinkedInPostMetadata(**metadata_dict)
            metadata.published = published
            if published:
                metadata.published_at = datetime.now(UTC)

            with metadata_file.open("w") as f:
                json.dump(metadata.model_dump(mode="json"), f, indent=2)

            logger.info("metadata_updated", pretalx_id=pretalx_id, published=published)

        except Exception as e:
            logger.error("failed_to_update_metadata", pretalx_id=pretalx_id, error=str(e))

    def publish_all(self, dry_run: bool = False, limit: int | None = None) -> dict:
        """Publish all prepared LinkedIn posts.

        Args:
            dry_run: If True, validate without posting
            limit: Maximum number to publish

        Returns:
            Statistics dictionary
        """
        stats = {"published": 0, "failed": 0, "published_ids": [], "failed_ids": []}

        # Get all prepared YAML files
        if not self.posts_dir.exists():
            logger.error("posts_directory_not_found", path=str(self.posts_dir))
            return stats

        yaml_files = sorted(self.posts_dir.glob("*.yaml"))

        if not yaml_files:
            logger.info("no_posts_to_publish")
            return stats

        if limit:
            yaml_files = yaml_files[:limit]

        logger.info("starting_batch_publish", total=len(yaml_files), limit=limit, dry_run=dry_run)

        for i, yaml_file in enumerate(yaml_files, 1):
            pretalx_id = yaml_file.stem

            logger.info("processing_post", index=i, total=len(yaml_files), pretalx_id=pretalx_id)

            try:
                success = self.publish_post(yaml_file, dry_run=dry_run)

                if success:
                    stats["published"] += 1
                    stats["published_ids"].append(pretalx_id)
                else:
                    stats["failed"] += 1
                    stats["failed_ids"].append(pretalx_id)

            except Exception as e:
                logger.error("batch_publish_error", pretalx_id=pretalx_id, error=str(e))
                stats["failed"] += 1
                stats["failed_ids"].append(pretalx_id)

        return stats


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Publish LinkedIn posts via influent CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Publish all prepared posts
  python -m src.pipeline.linkedin.publish_posts --all

  # Publish specific posts
  python -m src.pipeline.linkedin.publish_posts LRUKZQ.yaml 3CYZUH.yaml

  # Dry run (validate without posting)
  python -m src.pipeline.linkedin.publish_posts --all --dry-run

  # Limit number of posts
  python -m src.pipeline.linkedin.publish_posts --all --limit 5

Note:
  Before running this, ensure you have:
  1. Configured influent with LinkedIn credentials
  2. Authenticated via: influent --organization {org_name} auth
        """,
    )
    parser.add_argument("yaml_files", nargs="*", help="Specific YAML files to publish")
    parser.add_argument("--all", action="store_true", help="Publish all prepared posts")
    parser.add_argument("--dry-run", action="store_true", help="Validate without posting")
    parser.add_argument("--limit", type=int, help="Limit number of posts to publish")
    args = parser.parse_args()

    # Validate arguments
    if not args.all and not args.yaml_files:
        parser.error("Either specify YAML files or use --all")

    # Setup logging
    logger = setup_logging(module_name="linkedin.publish_posts")

    # Initialize publisher
    try:
        publisher = LinkedInPublisher()
    except ValueError as e:
        logger.error("initialization_failed", error=str(e))
        print(f"\nError: {e}")
        return 1

    # Process posts
    if args.all:
        logger.info("publishing_all_posts", dry_run=args.dry_run, limit=args.limit)
        stats = publisher.publish_all(dry_run=args.dry_run, limit=args.limit)

        logger.info(
            "batch_publish_complete",
            published=stats["published"],
            failed=stats["failed"],
            failed_ids=stats["failed_ids"],
        )

        if args.dry_run:
            print(f"\n✅ Dry run validated {stats['published']} LinkedIn posts")
        else:
            print(f"\n✅ Published {stats['published']} LinkedIn posts")

        if stats["failed"] > 0:
            print(f"⚠️  {stats['failed']} failed:")
            for pretalx_id in stats["failed_ids"]:
                print(f"    - {pretalx_id}")

    else:
        # Process specific files
        published = 0
        for filename in args.yaml_files:
            yaml_file = publisher.posts_dir / filename
            if publisher.publish_post(yaml_file, dry_run=args.dry_run):
                published += 1

        logger.info("publish_complete", requested=len(args.yaml_files), published=published)

        if published > 0:
            if args.dry_run:
                print(f"\n✅ Dry run validated {published} LinkedIn posts")
            else:
                print(f"\n✅ Published {published} LinkedIn posts")

    # Show status
    remaining = len(list(publisher.posts_dir.glob("*.yaml")))
    published_count = len(list(publisher.published_dir.glob("*.yaml")))

    print("\n📊 Status:")
    print(f"   {remaining} posts pending")
    print(f"   {published_count} posts published")

    return 0


if __name__ == "__main__":
    sys.exit(main())
