# CLAUDE.md

**⚠️ DEPRECATED: This file describes the OLD architecture that has been removed.**

**See [CLAUDE.local.md](CLAUDE.local.md) for current project structure and guidelines.**

---

## Historical Reference Only

This document is kept for historical reference. The old `src/manager/` module and CLI commands have been completely removed.

### What Changed

**OLD (Removed):**
- CLI commands: `pytube records fetch`, `pytube youtube map`, etc.
- `src/manager/` - handlers, scripts, CLI
- `src/models/` - old YouTube models

**NEW (Current):**
- Modular pipeline in `src/pipeline/`
- Direct Python module execution
- Modern architecture with clear separation of concerns

See [src/pipeline/README.md](src/pipeline/README.md) for current documentation.