#!/usr/bin/env bash
# Verification helpers for presentation_detector probe (run from repo root or any cwd).
# Usage:
#   ./scripts/verify_presentation_detector_probe.sh /path/to/recording.mp4 scan
#   ./scripts/verify_presentation_detector_probe.sh /path/to/recording.mp4 frames
#   ./scripts/verify_presentation_detector_probe.sh /path/to/recording.mp4 nomap
#
# Modes:
#   scan   — every 5 minutes, print scores (config threshold)
#   frames — probe at 0, 1h, 2h and save JPEGs under /tmp/probe_frames
#   nomap  — probe every 10 minutes without loading session Parquet

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Override with VERIFY_CONFIG for CI / minimal fixtures (see tests/fixtures/video_processor/verify_config.yaml).
CONFIG="${VERIFY_CONFIG:-${ROOT}/src/video_processor/config.yaml}"
VIDEO="${1:?Usage: $0 /path/to/recording.mp4 [scan|frames|nomap]}"
MODE="${2:-scan}"

if [[ ! -f "$CONFIG" ]]; then
  echo "Missing config: $CONFIG" >&2
  exit 1
fi
if [[ ! -f "$VIDEO" ]]; then
  echo "Missing video file: $VIDEO" >&2
  exit 1
fi

cd "$ROOT"

run() {
  uv run --extra video_processor python src/video_processor/presentation_detector.py \
    --config "$CONFIG" "$@"
}

case "$MODE" in
  scan)
    # Scan every 5 minutes and print scores (uses your config threshold)
    run --probe-video "$VIDEO" --probe-every 300
    ;;
  frames)
    # Save frames for eyeballing vs break PNGs
    mkdir -p /tmp/probe_frames
    run --probe-video "$VIDEO" --probe-times 0,3600,7200 --probe-save-frames /tmp/probe_frames
    ;;
  nomap)
    # No Parquet needed
    run --probe-video "$VIDEO" --probe-every 600 --probe-skip-mapping
    ;;
  *)
    echo "Unknown mode: $MODE (use scan, frames, or nomap)" >&2
    exit 1
    ;;
esac
