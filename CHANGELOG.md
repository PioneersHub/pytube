# Changelog

All notable changes to PyTube will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.0.0] - 2025-06-20

### Added
- Multi-provider AI support for content generation
  - OpenAI (GPT-3.5-turbo, GPT-4, GPT-4o)
  - Anthropic Claude (Opus, Sonnet, Haiku)
  - Google Gemini Pro
  - Cohere Command models
- Multi-platform social media posting
  - LinkedIn (existing)
  - Twitter/X
  - Mastodon 
  - Bluesky
- Event-based directory structure for multi-conference support
  - Data organized under `_tmp/{event_slug}/`
  - Migration utility for existing installations
  - Backward compatibility maintained
- AI-friendly CLI interfaces
  - Structured JSON responses for automation
  - Interactive setup wizard
  - Enhanced validation with specific configuration details
- Enhanced CLI assistant (`pytube enhanced`)
  - Named command support (use 'setup' instead of '1')
  - Context-aware menu options
  - Workflow management with persistence
  - Step selection for partial workflow execution
  - Progress tracking and recovery
- Enhanced setup wizard
  - Shows existing configuration values during reconfiguration
  - Provides options to Keep, Change, or Remove each value
  - Masks sensitive values (API keys, tokens) for security
  - Preserves untouched configuration during partial updates
  - Better handling of optional services
  - Added event configuration (name, URL, program URL)
  - Rich context for each configuration section explaining:
    - Why the information is needed
    - What features are enabled with it
    - What limitations exist without it
- Comprehensive documentation
  - API credentials guide with step-by-step instructions
  - Quick setup guide for beginners
  - Decision matrices for service selection
  - Updated CLI reference with assistant documentation

### Changed
- **BREAKING**: Separated AI description generation from records fetch command
  - `pytube records fetch` now only fetches data
  - Use `pytube records generate-descriptions` for AI content generation
  - Removed `--skip-descriptions` and `--replace-descriptions` flags from fetch
- Enhanced error handling and validation throughout the workflow
  - Commands now exit with proper error codes for automation
  - Added speaker loading validation to prevent incomplete records
  - Clear old data before fetching to ensure fresh state

### Fixed
- Assistant now correctly reports failures when records fetch fails
- Fixed exit codes to properly indicate success/failure for automation
- Improved error messages with actionable troubleshooting tips
- Added detailed statistics tracking (new vs updated records)
- Enhanced video organization system
  - New CLI commands: `assign-channels`, `move`, `report`
  - Dry-run mode for safe testing of file operations
  - Uses sibling directories for channel organization (pycon/, pydata/)
  - Improved video-to-session matching using first 6 characters
  - Automatic handling of do-not-record videos
  - Detailed reporting of unassigned videos
  - Fixed file move operations (was copying instead of moving)

### Changed
- Configuration now supports service selection
  - `ai_service` config option to choose AI provider
  - `social_media_service` config option for social platform
  - Model selection moved to configuration files
- Enhanced CLI assistant
  - Better validation messages showing actual values
  - Fixed command execution using CliRunner
  - Grouped service status display
- Directory structure improvements
  - All handlers now use event-specific paths
  - Records, videos, and social media queues organized by event

### Fixed
- CLI assistant command execution error (Group.invoke issue)
- Validation messages now show specific details instead of generic "configured"
- Path resolution for multi-project environments

## [0.1.0] - Previous Release

Initial release with basic YouTube video management functionality.