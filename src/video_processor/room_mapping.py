"""Pretalx room → short room-token mapping.

Default short form: strip any ``[...]`` annotation, strip whitespace, lowercase.
Hand-edit the generated YAML to customize per-room (e.g.
"Merck Plenary (Spectrum) [1st Floor]" → "spectrum" instead of the literal
default "merck plenary (spectrum)").
"""

import re
import sys
from pathlib import Path

import yaml

from manager import conf, logger

_BRACKET_RE = re.compile(r"\s*\[[^\]]*\]\s*")


def derive_short(room: str) -> str:
    """Default transform: drop any ``[...]`` annotation, strip, lowercase."""
    if not room:
        return ""
    return _BRACKET_RE.sub("", str(room)).strip().lower()


def _strip_brackets(room: str) -> str:
    """Drop any ``[...]`` annotation, strip whitespace — keeps original casing."""
    return _BRACKET_RE.sub("", str(room)).strip()


def build_mapping(rooms: list[str]) -> dict[str, str]:
    """Map every non-empty Pretalx room name — and its bracket-stripped
    (but case-preserved) form — to the default short form.

    Example input ``"Europium [3rd Floor]"`` yields both::

        "Europium [3rd Floor]": europium
        Europium: europium

    so consumers can look up either form against ``room_short``.
    """
    mapping: dict[str, str] = {}
    for room in rooms:
        if not room:
            continue
        short = derive_short(room)
        mapping[room] = short
        bare = _strip_brackets(room)
        if bare and bare != room:
            mapping[bare] = short
    return mapping


def generate(rooms: list[str], *, force: bool = False) -> Path | None:
    """Write the room-mapping YAML at ``pretalx.room_mapping_yaml``.

    If the file exists and ``force`` is False, prompts in an interactive TTY
    before overwriting; non-interactive keeps the existing file silently.
    Returns the written path, or ``None`` if the existing file was kept.
    """
    path_str = conf.pretalx.get("room_mapping_yaml", "") if hasattr(conf, "pretalx") else ""
    if not path_str:
        raise ValueError(
            "pretalx.room_mapping_yaml is not set. "
            "Add it to config.yaml / config_local.yaml — path where the mapping YAML will be written."
        )
    path = Path(path_str)

    if path.exists() and not force:
        if sys.stdin.isatty():
            answer = (
                input(
                    f"Room mapping already exists at {path}.\n"
                    "Regenerate? Hand edits WILL be lost. [y/N]: "
                )
                .strip()
                .lower()
            )
            if answer not in ("y", "yes"):
                logger.info(f"Keeping existing room mapping at {path}.")
                return None
        else:
            logger.info(f"Using existing room mapping at {path}.")
            return None

    mapping = build_mapping(rooms)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        f.write(
            "# Pretalx room -> short form. Hand-edit values as needed.\n"
            "# Default: strip [brackets], strip whitespace, lowercase.\n\n"
        )
        yaml.safe_dump(
            {"rooms": mapping}, f, sort_keys=False, allow_unicode=True, default_flow_style=False
        )
    logger.info(f"Wrote room mapping ({len(mapping)} rooms) to {path}")
    return path
