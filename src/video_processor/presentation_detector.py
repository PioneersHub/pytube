"""
Video Presentation Detector - Automatically detects and extracts presentations
from conference or livestream recordings by finding transitions between
break screens and presentations.

Supports batch processing of multiple videos from an input folder.
"""

import argparse
import json
import re
import subprocess
import time
import traceback
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import cv2
import numpy as np
import polars as pl
import yaml
from omegaconf import DictConfig, OmegaConf

from manager import logger

# Strip bracketed room annotations (same as process_talk_list / map_recordings).
_ROOM_ANNOTATION_RE = re.compile(r"\s*\[[^\]]*\]\s*")


def duration_nearest_slot_gap_min(duration_sec: float, expected_lengths_min: list[float]) -> float:
    """Minutes between detected segment length and the nearest expected slot (30/45/60/90, etc.)."""
    if not expected_lengths_min:
        return 0.0
    d_min = duration_sec / 60.0
    return min(abs(d_min - float(s)) for s in expected_lengths_min)


STANDARD_SLOT_MINUTES: tuple[int, ...] = (30, 45, 60, 90)

# Default (late_min, early_min) vs scheduled slot — see presentation_detection.schedule_slack_by_slot_min
_DEFAULT_SCHEDULE_SLACK: dict[int, tuple[float, float]] = {
    30: (5.0, 10.0),
    45: (5.0, 15.0),
    60: (10.0, 15.0),
    90: (10.0, 15.0),
}


def nearest_slot_minutes(duration_min: float) -> int:
    """Map a duration in minutes to the nearest standard slot (30/45/60/90)."""
    return min(STANDARD_SLOT_MINUTES, key=lambda s: abs(float(s) - duration_min))


def parse_pretalx_duration_to_seconds(value: str | None) -> float | None:  # noqa: PLR0911
    """
    Parse Pretalx ``Duration`` cell to seconds.
    Accepts integer minutes (``30``), decimal minutes, ``HH:MM``, ``HH:MM:SS``, ``MM:SS``.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if re.fullmatch(r"\d+", s):
        return float(s) * 60.0
    if re.fullmatch(r"\d+\.\d+", s):
        return float(s) * 60.0
    # Time-of-day style
    tail = s.split(" ")[-1] if " " in s else s
    parts = tail.replace(",", ".").split(":")
    try:
        if len(parts) == 3:  # noqa: PLR2004
            h, m, sec = (float(parts[0]), float(parts[1]), float(parts[2]))
            return h * 3600.0 + m * 60.0 + sec
        if len(parts) == 2:  # noqa: PLR2004
            m, sec = float(parts[0]), float(parts[1])
            return m * 60.0 + sec
    except ValueError:
        pass
    return None


def collect_video_paths(folder: Path, extensions: str) -> list[Path]:
    """Return sorted unique video paths for comma-separated extensions (case-insensitive)."""
    if not folder.is_dir():
        return []
    exts = [e.strip().lstrip(".").lower() for e in extensions.split(",") if e.strip()]
    seen: set[Path] = set()
    out: list[Path] = []
    for ext in exts:
        for pattern in (f"*.{ext}", f"*.{ext.upper()}"):
            for p in folder.glob(pattern):
                rp = p.resolve()
                if rp not in seen:
                    seen.add(rp)
                    out.append(p)
    out.sort(key=lambda p: p.as_posix().lower())
    return out


def get_video_files(input_folder: str, extensions: str) -> list[str]:
    """
    Get all video files from a folder with specified extensions

    Args:
        input_folder: Folder containing video files
        extensions: Comma-separated list of file extensions (e.g., "mp4,mkv")

    Returns:
        List of video file paths
    """
    input_path = Path(input_folder)
    if not input_path.is_dir():
        logger.info(f"Error: Input folder does not exist: {input_folder}")
        return []

    paths = collect_video_paths(input_path, extensions)
    video_files = [str(p) for p in paths]

    if not video_files:
        logger.info(f"No video files found in {input_folder} with extensions {extensions}")
    else:
        logger.info(f"Found {len(video_files)} video files in {input_folder}")

    return video_files


class VideoPresenterDetector:
    """Class for detecting presentations in videos using break screen detection"""

    def __init__(self, cfg: DictConfig):
        """Initialize with configuration"""
        self.cfg = cfg
        self.break_references = []
        self.mapping_data = None
        self._load_mapping_data()
        self.video_output_folder = Path(self.cfg.output.folder).resolve()
        self.video_output_folder.mkdir(parents=True, exist_ok=True)
        self.processing_plan_path = self.video_output_folder / "processing_plan.yaml"
        self.processing_plan = []
        self._video_fps: float | None = None
        self._video_total_frames: int | None = None
        self._detection_ref_arrays: list[np.ndarray] = []
        self._stats_frame_reads: int = 0
        self._stats_compare_calls: int = 0
        # Subset of break_references for presentation→break only (see end_ref_substrings).
        self.break_references_end: list[np.ndarray] = []
        self._detection_ref_arrays_end: list[np.ndarray] = []
        # Subset for session start: Pre-Session shared slide until it disappears (see start_ref_substrings).
        self.break_references_start: list[np.ndarray] = []
        self._detection_ref_arrays_start: list[np.ndarray] = []
        # Set by detect_all_presentations per video; prepended to in-flight detection logs.
        self._current_video: str | None = None
        # Last video duration (seconds) from detect_all_presentations — used for detection_quality.
        self._last_detected_video_duration_sec: float = 0.0
        # Max time for seeks (last frame), set in load_video — must match get_frame_at_time clamp.
        self._video_duration_scan: float = 0.0

    def _tag(self) -> str:
        return f"[{self._current_video}] " if self._current_video else ""

    @classmethod
    def get_video_files(cls, folder: Path, extensions: str) -> list[Path]:
        """
        Get all video files from a folder with specified extensions

        Args:
            folder: Folder containing video files
            extensions: Comma-separated list of file extensions (e.g., "mp4,mkv")

        Returns:
            List of video file paths
        """
        video_files = collect_video_paths(folder, extensions)

        if not video_files:
            logger.info(f"No video files found in {folder} with extensions {extensions}")
        else:
            logger.info(f"Found {len(video_files)} video files in {folder}")

        return video_files

    def load_video(self, video_path: str) -> tuple[cv2.VideoCapture, float, int, float]:
        """Open video file and return properties"""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Error: Could not open video {video_path}.")

        fps = float(cap.get(cv2.CAP_PROP_FPS)) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps else 0.0
        # Last readable frame time (matches get_frame_at_time clamp). Using nominal duration caused
        # seeks past the last frame → read failures treated as false "break" and bogus EOF cuts.
        self._video_duration_scan = (
            max(0.01, float(total_frames - 1) / fps) if total_frames > 0 and fps else float(duration or 0.0)
        )

        self._video_fps = fps
        self._video_total_frames = total_frames

        logger.info(f"Video loaded: {video_path}")
        logger.info(f"Duration: {timedelta(seconds=int(duration))}, FPS: {fps}")
        logger.info(f"Total frames: {total_frames}")

        return cap, fps, total_frames, duration

    def _detection_size_wh(self) -> tuple[int, int]:
        cfg = self.cfg.video
        ds = OmegaConf.select(cfg, "detection_size", default=None)
        if ds is not None:
            return int(ds[0]), int(ds[1])
        ps = cfg.processing_size
        return int(ps[0]), int(ps[1])

    def _use_detection_resize(self) -> bool:
        return bool(OmegaConf.select(self.cfg.video, "detection_resize", default=True))

    def _ensure_detection_frame(self, frame: np.ndarray) -> np.ndarray:
        """Resize frame for break comparison when detection_resize is enabled."""
        if not self._use_detection_resize():
            return frame
        w, h = self._detection_size_wh()
        if frame.shape[1] == w and frame.shape[0] == h:
            return frame
        return cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA)

    def _build_detection_arrays(self, refs: list[np.ndarray]) -> list[np.ndarray]:
        """Precompute per-reference arrays for fast is_break_screen (grayscale for template)."""
        out: list[np.ndarray] = []
        method = str(self.cfg.break_detection.comparison_method)
        for ref in refs:
            small = self._ensure_detection_frame(ref)
            match method:
                case "template":
                    out.append(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))
                case "histogram":
                    out.append(small)
                case _:
                    out.append(small)
        return out

    def _refresh_break_detection_refs(self) -> None:
        """Precompute caches for all-break vs end-of-talk vs session-start matching."""
        self._detection_ref_arrays = self._build_detection_arrays(self.break_references)
        self._detection_ref_arrays_end = self._build_detection_arrays(self.break_references_end)
        self._detection_ref_arrays_start = (
            self._build_detection_arrays(self.break_references_start) if self.break_references_start else []
        )

    def _assign_break_reference_subsets(self, image_files: list[Path], break_images: list[np.ndarray]) -> None:
        """Split refs: end-of-talk (room End-Stream), session-start (Pre-Session), and full set for generic use."""
        self.break_references = break_images
        end_subs: list[str] = list(
            OmegaConf.select(self.cfg.break_detection, "end_ref_substrings", default=[]) or []
        )
        # None/missing → default Pre-Session; explicit [] → disable start_break (use any_break for talk start).
        start_raw = OmegaConf.select(self.cfg.break_detection, "start_ref_substrings", default=None)
        if start_raw is None:
            start_subs = ["Pre-Session-Graphic-All-Rooms"]
        else:
            start_subs = [str(s).strip() for s in list(start_raw) if str(s).strip()]

        if not end_subs:
            self.break_references_end = list(break_images)
        else:
            end_indices = [
                i
                for i, p in enumerate(image_files)
                if any(s.lower() in p.name.lower() for s in end_subs if str(s).strip())
            ]
            if not end_indices:
                logger.warning(
                    "break_detection.end_ref_substrings is set but no image filenames matched; "
                    "using all break images for end-of-presentation detection"
                )
                self.break_references_end = list(break_images)
            else:
                self.break_references_end = [break_images[i] for i in end_indices]
                logger.info(
                    f"End-of-presentation refs: {len(self.break_references_end)} image(s) matching "
                    f"end_ref_substrings {end_subs!r}; other refs used for break→presentation / session start"
                )

        if not start_subs:
            self.break_references_start = []
            logger.info(
                "break_detection.start_ref_substrings is empty — talk start uses any_break (all loaded refs)"
            )
        else:
            start_indices = [
                i
                for i, p in enumerate(image_files)
                if any(s.lower() in p.name.lower() for s in start_subs)
            ]
            if not start_indices:
                self.break_references_start = []
                logger.warning(
                    f"break_detection.start_ref_substrings {start_subs!r} matched no files under images_dir; "
                    "session start will use any_break (all loaded refs). Add Pre-Session-Graphic PNGs or fix names."
                )
            else:
                self.break_references_start = [break_images[i] for i in start_indices]
                logger.info(
                    f"Session-start refs (Pre-Session → talk): {len(self.break_references_start)} image(s) matching "
                    f"{start_subs!r} — gallop/binary search for talk start uses these until the slide is gone"
                )

    def _room_names_longest_first(self) -> list[str]:
        """Room strings for matching video filenames (longest first, like map_recordings)."""
        rooms: list[str] = []
        if self.mapping_data is not None and len(self.mapping_data) > 0:
            try:
                if "Room" in self.mapping_data.columns:
                    raw = self.mapping_data.get_column("Room").drop_nulls().unique().to_list()
                    rooms = [_ROOM_ANNOTATION_RE.sub("", str(r)).strip() for r in raw if r]
                    rooms = sorted(set(rooms), key=len, reverse=True)
            except Exception as e:
                logger.info(f"Could not load rooms from mapping: {e}")
        if not rooms:
            extra = OmegaConf.select(self.cfg.break_detection, "room_names", default=None)
            if extra:
                rooms = sorted({str(x).strip() for x in list(extra) if str(x).strip()}, key=len, reverse=True)
        return rooms

    def _room_token_from_video_path(self, video_path: str) -> str | None:
        """Match longest room name contained in the recording path or stem."""
        stem = Path(video_path).stem
        hay = f"{video_path} {stem}".lower()
        for room in self._room_names_longest_first():
            r = room.strip()
            if not r:
                continue
            if r.lower() in hay:
                return r
        return None

    def _room_strings_for_image_match(self, room: str) -> list[str]:
        """Substrings to match PNG filenames; includes full label and parenthetical short name (e.g. Spectrum)."""
        room = room.strip()
        if not room:
            return []
        out: list[str] = [room]
        if "(" in room and ")" in room:
            inner = room[room.rfind("(") + 1 : room.rfind(")")].strip()
            if inner and inner not in out:
                out.append(inner)
        return out

    def _filter_break_image_paths_by_room(self, paths: list[Path], video_path: str | None) -> list[Path]:
        if not paths or not video_path:
            return paths
        if not bool(OmegaConf.select(self.cfg.break_detection, "filter_refs_by_room", default=True)):
            return paths
        room = self._room_token_from_video_path(video_path)
        if not room:
            logger.warning(
                "filter_refs_by_room: no room matched in video path; using all break images. "
                "Set break_detection.room_names or ensure input.mapping_file lists Room names."
            )
            return paths
        shared = list(
            OmegaConf.select(
                self.cfg.break_detection,
                "shared_ref_substrings",
                default=["All-Rooms", "Pre-Session-Graphic-All-Rooms"],
            )
        )
        tokens = self._room_strings_for_image_match(room)
        kept: list[Path] = []
        for p in paths:
            name = p.name
            if any(s in name for s in shared):
                kept.append(p)
                continue
            nl = name.lower()
            if any(t.lower() in nl for t in tokens):
                kept.append(p)
        if not kept:
            logger.warning(
                f"filter_refs_by_room: no images matched room {room!r}; using all {len(paths)} break images"
            )
            return paths
        logger.info(f"Room filter ({room}): using {len(kept)} of {len(paths)} break images")
        return kept

    def generate_processing_plan(self) -> list[dict]:
        """Generate and persist the processing plan for every raw video paired with its sessions."""
        self._load_mapping_data()
        single = OmegaConf.select(self.cfg.input, "video_path", default="")
        if single and str(single).strip():
            p = Path(str(single).strip()).expanduser().resolve()
            if not p.is_file():
                raise FileNotFoundError(f"input.video_path is not a file: {p}")
            video_files = [str(p)]
            logger.info(f"Single-video mode: processing only {p.name}")
        else:
            input_folder = Path(self.cfg.input.folder)
            video_files = self.get_video_files(input_folder, self.cfg.input.extensions)
        if not video_files:
            raise RuntimeError("No video files found (set input.folder or input.video_path)")

        processing_plan = []
        for video_path in video_files:
            output_folder = self.get_output_folder(video_path)
            if not output_folder:
                logger.info(f"No output folder in mapping for {video_path.name}; skipping")
                continue
            presentations = (
                self.mapping_data.filter(pl.col("Recording") == Path(video_path).name)
                .sort("Start (time)")
                .to_dicts()
            )
            processing_plan.append(
                {
                    "input_video": str(video_path),
                    "output_folder": str(output_folder),
                    "presentations": presentations,
                }
            )

        with self.processing_plan_path.open("w") as f:
            f.write("# Generated by presentation_detector.py — do not hand-edit while a run is in progress.\n\n")
            yaml.safe_dump(
                processing_plan, f, sort_keys=False, allow_unicode=True, default_flow_style=False
            )
        logger.info(f"Saved processing plan to {self.processing_plan_path}")
        return processing_plan

    def load_processing_plan(self) -> list[dict]:
        """Load the processing plan from YAML."""
        with self.processing_plan_path.open() as f:
            self.processing_plan = yaml.safe_load(f) or []
        return self.processing_plan

    def update_processing_plan(self, plan: dict) -> None:
        """Replace the entry matching plan['input_video'] and rewrite the YAML."""
        processing_plan = self.load_processing_plan()
        for i, p in enumerate(processing_plan):
            if p["input_video"] == plan["input_video"]:
                processing_plan[i] = plan
                break
        with self.processing_plan_path.open("w") as f:
            f.write("# Generated by presentation_detector.py — do not hand-edit while a run is in progress.\n\n")
            yaml.safe_dump(
                processing_plan, f, sort_keys=False, allow_unicode=True, default_flow_style=False
            )

    def extract_presentations_from_plan(self, *, extract_only: bool = False) -> None:
        """Extract clips using ``processing_plan.yaml`` (FFmpeg), only when detection passed quality gates.

        **Recommended workflow:** run detection first (``--detect-only`` or ``output.make_processing_plan``),
        inspect ``detection_quality`` in the plan file, then run ``--extract-only`` or enable
        ``output.extract_presentations`` separately.

        When ``extract_only`` is True, this never runs detection or generates a plan — it only reads
        the existing YAML and extracts. When ``output.auto_detect_on_extract`` is false (default),
        missing ``presentations_index`` or failed ``detection_quality`` skips extraction with an error
        instead of silently re-running detection.
        """
        if not self.processing_plan_path.exists():
            if extract_only:
                raise FileNotFoundError(
                    f"No processing plan at {self.processing_plan_path}. "
                    "Run detection first, e.g. `python presentation_detector.py --detect-only`."
                )
            logger.info(f"No processing plan at {self.processing_plan_path} — generating skeleton from mapping.")
            self.generate_processing_plan()

        self.load_processing_plan()
        auto_detect = bool(OmegaConf.select(self.cfg, "output.auto_detect_on_extract", default=False))

        for plan in self.processing_plan:
            if not plan.get("presentations"):
                continue

            idx = plan.get("presentations_index")
            dq = plan.get("detection_quality") or {}

            if not idx:
                if extract_only or not auto_detect:
                    logger.error(
                        f"Skipping {plan.get('input_video')}: no presentations_index in plan. "
                        "Run detection first (`--detect-only`), or set output.auto_detect_on_extract: true to allow "
                        "auto-detection from this step (not recommended)."
                    )
                    continue
                logger.info(f"Detecting presentations in {plan['input_video']} (auto_detect_on_extract=true)...")
                if not self.process_video(plan):
                    logger.warning(f"Detection failed for {plan['input_video']}; skipping.")
                    continue
                idx = plan.get("presentations_index")
                dq = plan.get("detection_quality") or {}

            if not idx:
                logger.error(f"Skipping {plan.get('input_video')}: no presentations_index after detection step.")
                continue

            if dq.get("passed") is False:
                logger.error(
                    f"Skipping {plan.get('input_video')}: detection_quality.passed is false — "
                    "fix break detection and re-run detection before FFmpeg extract."
                )
                continue

            if dq.get("passed") is None:
                vdur = float(plan.get("video_duration_sec") or 0.0)
                passed, new_dq = self.evaluate_detection_quality(plan, idx, vdur)
                if not passed:
                    new_dq["candidate_segments"] = [[float(s), float(e)] for s, e in idx]
                plan["detection_quality"] = new_dq
                self.update_processing_plan(plan)
                if not passed:
                    logger.error(
                        f"Skipping extract for {plan.get('input_video')}: legacy plan fails detection_quality re-check."
                    )
                    continue

            logger.info(f"Extracting presentations from {plan['input_video']}...")
            self.extract_presentations(plan)

    def process_video(self, plan: dict) -> bool:
        """
        Process a single video file according to the processing plan

        Args:
            plan: Plan to process to the video file

        Returns:
            True if processing was successful, False otherwise
        """
        try:
            logger.info(f"PROCESSING VIDEO: {plan.get('input_video')}")
            (self.video_output_folder / plan["output_folder"]).mkdir(parents=True, exist_ok=True)

            # Detect presentations
            presentations_index = self.detect_all_presentations(plan)
            video_dur = float(self._last_detected_video_duration_sec)
            plan["video_duration_sec"] = video_dur

            logger.info(f"Found {len(presentations_index)} presentation segment(s) (scheduled rows: {len(plan['presentations'])})")

            passed, dq_report = self.evaluate_detection_quality(plan, presentations_index, video_dur)
            if not passed:
                dq_report["candidate_segments"] = [[float(s), float(e)] for s, e in presentations_index]
            plan["detection_quality"] = dq_report

            session_report = self.build_session_report(plan, len(presentations_index), passed)
            session_report["quality_failure_codes"] = dq_report.get("failure_codes", [])
            session_report["quality_failure_reasons"] = dq_report.get("failure_reasons", [])
            session_report["quality_limits"] = dq_report.get("limits", {})
            plan["session_report"] = session_report
            self._log_session_report(session_report)
            self._append_session_report_jsonl(session_report)

            if not passed:
                plan.pop("presentations_index", None)
                self.update_processing_plan(plan)
                logger.error(
                    f"Processing aborted for {plan.get('input_video')}: detection quality gate failed "
                    f"(see detection_quality in {self.processing_plan_path}). No FFmpeg extract will run until fixed."
                )
                return False

            plan["presentations_index"] = presentations_index
            self.update_processing_plan(plan)

            # Save metadata if configured
            if presentations_index and self.cfg.output.save_metadata:
                self.save_presentation_metadata(plan, presentations_index)
            return True

        except Exception as e:
            logger.info(f"Error processing video {plan.get('input_video')}: {str(e)}")
            traceback.print_exc()
            try:
                sr = self.build_session_report(plan, 0, False)
                plan["session_report"] = sr
                plan["detection_quality"] = plan.get("detection_quality") or {
                    "passed": False,
                    "failure_reasons": [f"exception: {e}"],
                }
                self._log_session_report(sr)
                self._append_session_report_jsonl(sr)
                self.update_processing_plan(plan)
            except Exception:
                pass
            return False

    def get_frame_at_time(self, cap: cv2.VideoCapture, time_sec: float) -> np.ndarray | None:
        """Get a frame at a specific time in the video"""
        self._stats_frame_reads += 1
        fps = self._video_fps if self._video_fps is not None else float(cap.get(cv2.CAP_PROP_FPS)) or 30.0
        if self._video_total_frames is not None and fps > 0:
            max_t = max(0.0, float(self._video_total_frames - 1) / fps)
            time_sec = max(0.0, min(float(time_sec), max_t))
        use_msec = bool(OmegaConf.select(self.cfg.video, "seek_use_pos_msec", default=False))
        if use_msec:
            cap.set(cv2.CAP_PROP_POS_MSEC, float(time_sec) * 1000.0)
        else:
            frame_pos = int(float(time_sec) * fps)
            if self._video_total_frames is not None:
                frame_pos = max(0, min(frame_pos, self._video_total_frames - 1))
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
        ret, frame = cap.read()
        if not ret:
            logger.info(f"WARNING: Could not read frame at {time_sec}s")
            return None

        if self.cfg.video.enable_resize:
            width, height = self.cfg.video.processing_size
            return cv2.resize(frame, (width, height))

        return frame

    def load_break_images(self, break_images_dir: str, video_path: str | None = None) -> list[np.ndarray]:
        """Load break images from a directory.

        When ``video_path`` is set and ``break_detection.filter_refs_by_room`` is true,
        only images for that video's room (plus shared refs) are loaded, reducing
        template-matching work substantially.
        """
        if not break_images_dir:
            logger.info("No break images directory provided")
            self.break_references = []
            self.break_references_end = []
            self.break_references_start = []
            return []

        break_images_path = Path(break_images_dir)
        if not break_images_path.is_dir():
            logger.info(f"Break images directory does not exist: {break_images_dir}")
            self.break_references = []
            self.break_references_end = []
            self.break_references_start = []
            return []

        logger.info(f"Loading break images from {break_images_dir}...")
        image_files: list[Path] = []
        for pattern in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"):
            image_files.extend(break_images_path.glob(pattern))
        image_files = sorted({p.resolve(): p for p in image_files}.values(), key=lambda p: p.name.lower())
        image_files = self._filter_break_image_paths_by_room(image_files, video_path)

        if not image_files:
            logger.info(f"No images found in {break_images_dir}")
            self.break_references = []
            self.break_references_end = []
            self.break_references_start = []
            return []

        break_images = []

        for img_path in image_files:
            name = img_path.name
            img = cv2.imread(str(img_path))
            if img is not None:
                # Only resize if enabled
                if self.cfg.video.enable_resize:
                    width, height = self.cfg.video.processing_size
                    img = cv2.resize(img, (width, height))

                break_images.append(img)
                logger.info(f"  Loaded: {name}")

        logger.info(f"✅ Loaded {len(break_images)} break images")
        self._assign_break_reference_subsets(image_files, break_images)
        return break_images

    def detect_break_screens(self, cap: cv2.VideoCapture, _fps: float, duration: float) -> list[np.ndarray]:
        """
        Detect multiple possible break screens by sampling the video
        and clustering similar frames
        """
        logger.info("Detecting potential break screens...")

        cfg = self.cfg.presentation_detection
        # Sample frames throughout the video
        sample_frames = []
        sample_times = []

        # Limit the number of samples for very long videos
        actual_interval = max(cfg.sampling_interval, duration / cfg.max_samples)

        for time_sec in np.arange(0, duration, actual_interval):
            frame = self.get_frame_at_time(cap, time_sec)
            if frame is not None:
                sample_frames.append(frame)
                sample_times.append(time_sec)

        logger.info(f"Collected {len(sample_frames)} sample frames")

        # Find clusters of similar frames
        clusters = defaultdict(list)
        cluster_refs = []

        for i, frame in enumerate(sample_frames):
            # Check if this frame is similar to any existing cluster
            found_cluster = False
            for cluster_id, ref_frame in enumerate(cluster_refs):
                similarity = self.compare_frames(frame, ref_frame)
                if similarity > cfg.cluster_threshold:
                    clusters[cluster_id].append(i)
                    found_cluster = True
                    break

            # If not similar to any cluster, create a new one
            if not found_cluster:
                cluster_id = len(cluster_refs)
                cluster_refs.append(frame)
                clusters[cluster_id].append(i)

        # Calculate average frames for each cluster and count frequency
        break_candidates = []
        cluster_stats = []

        min_cluster_size = 3
        for cluster_id, frame_indices in clusters.items():
            if len(frame_indices) < min_cluster_size:
                # Skip small clusters (likely not break screens)
                continue

            # Get all frames in this cluster
            cluster_frames = [sample_frames[i] for i in frame_indices]

            # Calculate average frame
            avg_frame = np.mean(cluster_frames, axis=0).astype(np.uint8)

            # Calculate cluster stats
            frequency = len(frame_indices) / len(sample_frames)
            avg_duration = self._estimate_cluster_duration(frame_indices, sample_times, actual_interval)

            cluster_stats.append(
                {
                    "id": cluster_id,
                    "size": len(frame_indices),
                    "frequency": frequency,
                    "avg_duration": avg_duration,
                    "first_occurrence": sample_times[frame_indices[0]],
                }
            )

            break_candidates.append(avg_frame)

        # Sort clusters by likelihood of being break screens (larger and more frequent clusters first)
        sorted_indices = sorted(
            range(len(cluster_stats)),
            key=lambda i: (cluster_stats[i]["frequency"], cluster_stats[i]["avg_duration"]),
            reverse=True,
        )

        # Get the most likely break screens
        top_break_screens = [break_candidates[i] for i in sorted_indices]

        # logger.info cluster statistics
        logger.info("Potential break screen statistics:")
        for i, idx in enumerate(sorted_indices):
            stats = cluster_stats[idx]
            logger.info(
                f"Break screen candidate {i + 1}: {stats['size']} occurrences "
                + f"({stats['frequency'] * 100:.1f}% of samples), "
                + f"avg duration ~{stats['avg_duration']:.1f}s, "
                + f"first seen at {timedelta(seconds=int(stats['first_occurrence']))}"
            )

        # Save the top break screens for verification
        detected_dir = Path(self.cfg.break_detection.detected_screens_dir)
        detected_dir.mkdir(parents=True, exist_ok=True)
        for i, screen in enumerate(top_break_screens):
            cv2.imwrite(str(detected_dir / f"break_screen_{i + 1}.jpg"), screen)

        logger.info(f"✅ Detected {len(top_break_screens)} potential break screens")
        logger.info(f"Break screen images saved to {detected_dir}/ directory for verification")

        return top_break_screens

    def _estimate_cluster_duration(self, frame_indices: list[int], _sample_times: list[float], interval: float) -> float:
        """Estimate the average duration of frames in a cluster"""
        if len(frame_indices) <= 1:
            return 0

        # Find consecutive frames in the cluster
        durations = []
        consecutive_count = 1

        for i in range(1, len(frame_indices)):
            if frame_indices[i] == frame_indices[i - 1] + 1:
                consecutive_count += 1
            else:
                if consecutive_count > 1:
                    durations.append(consecutive_count * interval)
                consecutive_count = 1

        if consecutive_count > 1:
            durations.append(consecutive_count * interval)

        return np.mean(durations) if durations else 0

    def compare_frames(self, frame1: np.ndarray, frame2: np.ndarray) -> float:
        """Compare two frames and return similarity score (0-1)"""
        self._stats_compare_calls += 1
        a = self._ensure_detection_frame(frame1)
        b = self._ensure_detection_frame(frame2)
        method = str(self.cfg.break_detection.comparison_method)
        match method:
            case "template":
                g1 = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
                g2 = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
                result = cv2.matchTemplate(g1, g2, cv2.TM_CCOEFF_NORMED)
                return float(np.max(result))
            case "histogram":
                hist1 = cv2.calcHist([a], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
                hist1 = cv2.normalize(hist1, hist1).flatten()
                hist2 = cv2.calcHist([b], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
                hist2 = cv2.normalize(hist2, hist2).flatten()
                return float(cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL))
            case _:
                raise ValueError(f"Unknown comparison method: {method}")

    def _threshold_for_break_purpose(self, purpose: str) -> float:
        """Optional per-purpose overrides (tune Pre-Session vs End-Stream without affecting the other)."""
        base = float(self.cfg.break_detection.threshold)
        if purpose == "start_break":
            o = OmegaConf.select(self.cfg.break_detection, "start_threshold", default=None)
            return float(o) if o is not None else base
        if purpose == "end_break":
            o = OmegaConf.select(self.cfg.break_detection, "end_threshold", default=None)
            return float(o) if o is not None else base
        return base

    def is_break_screen(  # noqa: PLR0911, PLR0912
        self,
        frame: np.ndarray | None,
        purpose: str = "any_break",
        *,
        threshold_relax: float = 0.0,
    ) -> tuple[bool, float, int]:
        """
        Check if a frame matches break reference images.

        ``any_break``: all loaded refs — generic (initial state, fallbacks).
        ``start_break``: only ``start_ref_substrings`` (default Pre-Session-Graphic) — the slide that
        marks session start; gallop finds when it is **no longer** displayed (break→presentation).
        ``end_break``: only ``end_ref_substrings`` (e.g. End-Stream per room) — presentation→break.
        """
        if purpose == "start_break" and not self.break_references_start:
            return self.is_break_screen(frame, "any_break")

        if purpose == "any_break":
            break_references = self.break_references
            detection_arrays = self._detection_ref_arrays
        elif purpose == "end_break":
            break_references = self.break_references_end
            detection_arrays = self._detection_ref_arrays_end
        elif purpose == "start_break":
            break_references = self.break_references_start
            detection_arrays = self._detection_ref_arrays_start
        else:
            raise ValueError(f"Unknown is_break_screen purpose: {purpose!r}")

        threshold = max(0.08, self._threshold_for_break_purpose(purpose) - float(threshold_relax))

        if frame is None:
            # Do not classify read failures as break — that created false transitions at EOF/garbled seeks.
            return False, 0.0, -1

        best_score = 0.0
        best_index = -1

        if detection_arrays and len(detection_arrays) == len(break_references):
            small = self._ensure_detection_frame(frame)
            method = str(self.cfg.break_detection.comparison_method)
            match method:
                case "template":
                    g = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                    for i, refg in enumerate(detection_arrays):
                        result = cv2.matchTemplate(g, refg, cv2.TM_CCOEFF_NORMED)
                        score = float(np.max(result))
                        if score > threshold:
                            return True, score, i
                        if score > best_score:
                            best_score = score
                            best_index = i
                    return False, best_score, best_index
                case "histogram":
                    for i, ref_small in enumerate(detection_arrays):
                        hist1 = cv2.calcHist([small], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
                        hist1 = cv2.normalize(hist1, hist1).flatten()
                        hist2 = cv2.calcHist([ref_small], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
                        hist2 = cv2.normalize(hist2, hist2).flatten()
                        score = float(cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL))
                        if score > threshold:
                            return True, score, i
                        if score > best_score:
                            best_score = score
                            best_index = i
                    return False, best_score, best_index
                case _:
                    pass

        for i, ref in enumerate(break_references):
            similarity = self.compare_frames(frame, ref)
            if similarity > threshold:
                return True, similarity, i
            if similarity > best_score:
                best_score = similarity
                best_index = i

        is_break = best_score > threshold
        return is_break, best_score, best_index

    def _advance_to_pre_session_if_needed(self, cap: cv2.VideoCapture, t0: float, scan_end: float) -> float:
        """
        After an End-Stream, interstitial may show Logo/Welcome before Pre-Session. For ``start_break``
        gallop we must not treat "not Pre-Session yet" as "already in talk" — scan forward until
        Pre-Session is visible, or return ``t0`` if we should fall back to ``any_break``.
        """
        if not self.break_references_start:
            return t0
        chunk = float(self.cfg.presentation_detection.chunk_size)
        t = float(t0)
        while t < scan_end - 1e-6:
            fr = self.get_frame_at_time(cap, t)
            pre, _, _ = self.is_break_screen(fr, "start_break")
            any_br, _, _ = self.is_break_screen(fr, "any_break")
            if pre:
                return t
            if not any_br:
                return t0
            t += chunk
        return t0

    def _gallop_first_state_change(
        self,
        cap: cv2.VideoCapture,
        t_start: float,
        scan_end: float,
        start_is_break: bool,
    ) -> tuple[float, float] | None:
        """
        From t_start (inclusive) where break-state is start_is_break, advance until the state flips
        or ``scan_end``. Returns (prev_time, next_time) bracketing one transition.

        ``scan_end`` is typically ``video_duration`` or a schedule-derived bound (first plausible End-Stream).

        When ``start_is_break`` is True and Pre-Session refs exist, we advance to the first frame where
        Pre-Session is visible (skipping Logo/Welcome-only interstitial), then gallop until Pre-Session
        is gone. If no Pre-Session appears before ``any_break`` goes false, fall back to ``any_break``.
        """
        purpose: str
        t0 = float(t_start)
        if start_is_break and self.break_references_start:
            t_sync = self._advance_to_pre_session_if_needed(cap, t0, scan_end)
            fr0 = self.get_frame_at_time(cap, t_sync)
            pre0, _, _ = self.is_break_screen(fr0, "start_break")
            any0, _, _ = self.is_break_screen(fr0, "any_break")
            if pre0:
                purpose = "start_break"
                t0 = t_sync
            elif not any0:
                purpose = "any_break"
            else:
                purpose = "any_break"
        elif start_is_break:
            purpose = "any_break"
        else:
            purpose = "end_break"
        chunk = float(self.cfg.presentation_detection.chunk_size)
        raw_max = float(OmegaConf.select(self.cfg, "presentation_detection.gallop_max_step", default=3600.0))
        # If max_step <= chunk, min(step*2, max_step) never exceeds chunk → degenerates to a fixed chunk scan.
        max_step = max(raw_max, chunk * 2.0)
        prev = float(t0)
        step = chunk
        expected_state = start_is_break
        # For start_break, "in break" means Pre-Session visible (True); gallop expects that at prev.
        if purpose == "start_break":
            frs = self.get_frame_at_time(cap, prev)
            start_in_ps, _, _ = self.is_break_screen(frs, "start_break")
            if not start_in_ps:
                return None
            expected_state = True
        while prev < scan_end - 1e-9:
            nxt = min(prev + step, scan_end)
            fr = self.get_frame_at_time(cap, nxt)
            is_br, _, _ = self.is_break_screen(fr, purpose)
            if is_br != expected_state:
                return (prev, nxt)
            prev = nxt
            step = min(step * 2.0, max_step)
            if nxt >= scan_end - 1e-9:
                break
        return None

    def _get_schedule_slack_minutes(self, slot_min: int) -> tuple[float, float]:
        """Return (late_min, early_min) for a standard slot; optional YAML override."""
        o = OmegaConf.select(self.cfg, "presentation_detection.schedule_slack_by_slot_min", default=None)
        if o is not None:
            for key in (slot_min, str(slot_min)):
                if key in o:
                    v = o[key]
                    if isinstance(v, (list, tuple)) and len(v) >= 2:  # noqa: PLR2004
                        return float(v[0]), float(v[1])
        return _DEFAULT_SCHEDULE_SLACK.get(slot_min, (10.0, 15.0))

    def _use_schedule_duration_for_end_search(self) -> bool:
        return bool(
            OmegaConf.select(self.cfg, "presentation_detection.use_schedule_duration_for_end_search", default=True)
        )

    def build_session_report(
        self,
        plan: dict,
        segments_found: int,
        quality_passed: bool | None,
    ) -> dict:
        """
        Per-video session counts vs the schedule (``plan['presentations']``).

        *sessions_missed* = max(0, expected − found). *segments_surplus* = max(0, found − expected).
        """
        expected = len(plan.get("presentations") or [])
        found = int(segments_found)
        missed = max(0, expected - found)
        surplus = max(0, found - expected)
        return {
            "file": Path(plan["input_video"]).name,
            "input_video": plan["input_video"],
            "sessions_expected": expected,
            "segments_found": found,
            "sessions_missed": missed,
            "segments_surplus_vs_schedule": surplus,
            "quality_passed": quality_passed,
        }

    def _log_session_report(self, report: dict) -> None:
        """Emit a clear block in logs for ``--detect-only`` / batch runs."""
        sep = "=" * 78
        qp = report.get("quality_passed")
        qstr = "PASS" if qp is True else ("FAIL" if qp is False else "N/A")
        logger.info(sep)
        logger.info(f"SESSION DETECTION REPORT | {report['file']}")
        logger.info(f"  Sessions expected (from schedule):  {report['sessions_expected']}")
        logger.info(f"  Presentation segments found:        {report['segments_found']}")
        logger.info(f"  Sessions missed (vs schedule):    {report['sessions_missed']}")
        logger.info(f"  Segments over schedule (surplus):   {report['segments_surplus_vs_schedule']}")
        logger.info(f"  Quality gate:                       {qstr}")
        codes = report.get("quality_failure_codes")
        reasons = report.get("quality_failure_reasons")
        if qp is False and reasons:
            logger.info(f"  Failure codes:                      {codes}")
            for line in reasons:
                logger.info(f"    · {line}")
        logger.info(sep)

    def _append_session_report_jsonl(self, report: dict) -> None:
        """Append one JSON object per line under ``output.folder`` for scripting."""
        path = self.video_output_folder / "detection_session_report.jsonl"
        line = json.dumps(report, ensure_ascii=False) + "\n"
        with path.open("a", encoding="utf-8") as f:
            f.write(line)

    def evaluate_detection_quality(  # noqa: PLR0912, PLR0915
        self,
        plan: dict,
        segments: list[tuple[float, float]],
        video_duration_sec: float,
    ) -> tuple[bool, dict]:
        """
        Hard quality gate before any FFmpeg extract. Returns (passed, report) with YAML-safe dict.

        Fails obviously broken runs (e.g. one 3h segment when three sessions are scheduled).
        """
        dq = OmegaConf.select(self.cfg, "presentation_detection.detection_quality", default=None)
        if dq is None:
            dq = OmegaConf.create({})
        enabled = bool(OmegaConf.select(dq, "enabled", default=True))
        expected = len(plan.get("presentations") or [])
        got = len(segments)
        failure_reasons: list[str] = []
        checks: dict[str, object] = {}

        report: dict = {
            "passed": True,
            "expected_sessions": expected,
            "detected_segments": got,
            "video_duration_sec": round(float(video_duration_sec), 3) if video_duration_sec > 0 else None,
            "failure_reasons": failure_reasons,
            "checks": checks,
        }

        if not enabled:
            report["passed"] = True
            report["skipped"] = True
            return True, report

        fail_count = bool(OmegaConf.select(dq, "fail_on_count_mismatch", default=True))
        max_seg_min = float(
            OmegaConf.select(
                dq,
                "max_segment_duration_min",
                default=float(
                    OmegaConf.select(self.cfg, "presentation_detection.max_presentation_duration_min", default=90.0)
                )
                + 30.0,
            )
        )
        frac_limit = float(OmegaConf.select(dq, "fail_single_segment_max_video_fraction", default=0.72))

        # --- Count
        count_ok = expected == got
        checks["count_match"] = {
            "ok": count_ok,
            "expected": expected,
            "got": got,
        }
        if fail_count and not count_ok:
            msg = f"session count mismatch: expected {expected} scheduled row(s), detector produced {got} segment(s)"
            failure_reasons.append(msg)

        # --- Per-segment duration cap (absolute)
        # One scheduled row covering the whole file (e.g. half-day track) may exceed a nominal cap.
        seg_dur_ok = True
        skip_cap = expected == 1 and got == 1 and len(segments) == 1
        for i, (start, end) in enumerate(segments):
            if skip_cap:
                continue
            dur_min = (end - start) / 60.0
            if dur_min > max_seg_min + 1e-6:
                seg_dur_ok = False
                msg = (
                    f"segment {i + 1} length {dur_min:.1f} min exceeds "
                    f"detection_quality.max_segment_duration_min ({max_seg_min:.0f} min)"
                )
                failure_reasons.append(msg)
        checks["max_segment_duration"] = {
            "ok": seg_dur_ok,
            "limit_min": max_seg_min,
            "skipped_single_full_file": skip_cap,
        }

        # --- Multiple sessions scheduled but one huge segment (merged talks / missed End-Stream)
        merge_ok = True
        if (
            expected > 1
            and got == 1
            and segments
            and video_duration_sec > 60.0  # noqa: PLR2004
            and frac_limit > 0.0
        ):
            span = segments[0][1] - segments[0][0]
            frac = span / video_duration_sec
            merge_ok = frac <= frac_limit
            checks["single_segment_vs_multi_expected"] = {
                "ok": merge_ok,
                "segment_fraction_of_file": round(frac, 4),
                "limit": frac_limit,
            }
            if not merge_ok:
                failure_reasons.append(
                    f"expected {expected} sessions but only 1 segment covering {frac * 100:.1f}% of the file "
                    f"(limit {frac_limit * 100:.0f}%) — likely missed End-Stream cuts; tune break_detection"
                )

        failure_codes: list[str] = []
        if fail_count and not count_ok:
            failure_codes.append("count_mismatch")
        if not seg_dur_ok:
            failure_codes.append("max_segment_duration")
        if expected > 1 and got == 1 and segments and not merge_ok:
            failure_codes.append("single_segment_covers_file")

        passed = not failure_reasons
        report["passed"] = passed
        report["failure_codes"] = failure_codes
        report["limits"] = {
            "max_segment_duration_min": max_seg_min,
            "fail_single_segment_max_video_fraction": frac_limit,
        }
        if not passed:
            for msg in failure_reasons:
                logger.error(f"DETECTION QUALITY FAIL: {msg}")
            logger.error(
                f"DETECTION QUALITY summary: codes={failure_codes} — "
                "these gates fire when the detector output does not match the schedule. "
                "Most often: Pre-Session (start_ref_substrings) or End-Stream (end_ref_substrings) not matched "
                "between talks (see break_detection.threshold / start_threshold / end_threshold, "
                "comparison_method, room-filtered refs). "
                "count_mismatch alone means fewer (or more) cuts than scheduled rows."
            )
        else:
            logger.info(
                f"Detection quality OK: {got} segment(s), expected {expected}, "
                f"max_segment_cap={max_seg_min:.0f} min"
            )
        return passed, report

    def binary_search_transition(
        self,
        cap: cv2.VideoCapture,
        start_time: float,
        end_time: float,
        target_is_break: bool,
        *,
        threshold_relax: float = 0.0,
    ) -> tuple[float, int]:
        """
        Binary search to find transition point between break and presentation
        """
        purpose = (
            "end_break"
            if target_is_break
            else ("start_break" if self.break_references_start else "any_break")
        )
        relax_use = float(threshold_relax) if target_is_break else 0.0
        min_interval = self.cfg.presentation_detection.min_interval

        current_start = start_time
        current_end = end_time

        logger.info(f"Binary search from {timedelta(seconds=int(start_time))} to {timedelta(seconds=int(end_time))}")
        logger.info(
            f"Looking for {'presentation→break' if target_is_break else 'break→presentation'} transition "
            f"(purpose={purpose}"
            + (f", end_break threshold_relax={relax_use:.3f}" if relax_use > 0 else "")
            + ")"
        )

        best_match_overall = -1
        iteration = 1
        while current_end - current_start > min_interval:
            mid_time = (current_start + current_end) / 2
            mid_frame = self.get_frame_at_time(cap, mid_time)

            is_break, score, best_match = self.is_break_screen(
                mid_frame, purpose, threshold_relax=relax_use
            )
            if best_match > -1:
                best_match_overall = best_match

            # Nice formatted time for logging
            mid_time_str = str(timedelta(seconds=int(mid_time)))
            interval_size = current_end - current_start

            logger.info(
                f"Iteration {iteration}: Checking at {mid_time_str} "
                + f"[{interval_size:.1f}s interval] → {'BREAK' if is_break else 'PRESENTATION'} "
                + f"(score: {score:.3f}, ref: {best_match + 1 if best_match >= 0 else 'N/A'})"
            )

            if (target_is_break and is_break) or (not target_is_break and not is_break):
                # We found what we're looking for, search in first half
                current_end = mid_time
            else:
                # Not what we're looking for, search in second half
                current_start = mid_time

            iteration += 1

        # Final result: take the midpoint of the final interval
        result = (current_start + current_end) / 2

        logger.info(
            f"✅ Found transition at {timedelta(seconds=int(result))}"
            + f" (break screen type: {best_match_overall + 1 if best_match_overall >= 0 else 'N/A'})"
        )
        return result, best_match_overall

    def find_next_presentation(  # noqa: PLR0915, PLR0911
        self,
        cap: cv2.VideoCapture,
        current_time: float,
        video_duration: float,
        expected_session: dict | None = None,
        *,
        scheduled_session_count: int = 0,
        closing_segment_index: int = 0,
    ) -> tuple[float, float, int, int] | None:
        """
        Find the next presentation in the video.

        ``expected_session`` is the matching row from ``processing_plan.yaml`` ``presentations`` (Pretalx CSV),
        used to bound End-Stream search via ``Duration`` when enabled.

        ``scheduled_session_count`` / ``closing_segment_index``: when the schedule lists multiple sessions
        and End-Stream never matches on the file, the end of talk one can still be placed at the same
        **Pre-Session → talk** edge used for every session start (``start_break``), with a dense time
        grid so short interstitials are not skipped.
        """
        chunk_size = float(self.cfg.presentation_detection.chunk_size)

        tag = self._tag()
        logger.info(f"{'=' * 80}")
        logger.info(f"{tag}Searching for next presentation starting from {timedelta(seconds=int(current_time))}")
        logger.info(f"{'=' * 80}")

        if current_time >= video_duration - chunk_size / 2:
            logger.info(f"{tag}Reached end of video, no more presentations to find")
            return None

        search_time = current_time
        start_frame = self.get_frame_at_time(cap, search_time)
        is_break, score, break_type = self.is_break_screen(start_frame, "any_break")

        logger.info(
            f"{tag}Current position at {timedelta(seconds=int(search_time))} is "
            + f"{'BREAK' if is_break else 'PRESENTATION'} "
            + f"(score: {score:.3f}, ref: {break_type + 1 if break_type >= 0 else 'N/A'})"
        )

        if not is_break:
            logger.info(f"{tag}Currently in a presentation, finding its end first...")
            bracket = self._gallop_first_state_change(cap, search_time, video_duration, start_is_break=False)
            if bracket is None:
                if bool(
                    OmegaConf.select(
                        self.cfg,
                        "presentation_detection.fallback_segment_if_no_end_stream",
                        default=True,
                    )
                ):
                    logger.warning(
                        f"{tag}No End-Stream transition found before EOF (threshold/refs may miss slides, "
                        f"or file is one continuous talk). Using single segment "
                        f"{timedelta(seconds=int(search_time))} → {timedelta(seconds=int(video_duration))}."
                    )
                    return (search_time, video_duration, -1, -1)
                logger.info(f"{tag}Reached end of video during initial search")
                return None
            prev_t, next_t = bracket
            logger.info(
                f"{tag}Found potential end of current presentation around {timedelta(seconds=int(next_t))}"
            )
            presentation_end, end_break_type = self.binary_search_transition(cap, prev_t, next_t, True)
            search_time = presentation_end
            is_break = True
            break_type = end_break_type

        if is_break:
            logger.info("Searching for start of next presentation...")
            start_break_type = break_type

            bracket = self._gallop_first_state_change(cap, search_time, video_duration, start_is_break=True)
            if bracket is None:
                logger.info("Reached end of video during initial search")
                return None
            prev_t, next_t = bracket
            search_frame = self.get_frame_at_time(cap, next_t)
            probe_purpose = "start_break" if self.break_references_start else "any_break"
            is_br_next, score, break_type = self.is_break_screen(search_frame, probe_purpose)
            logger.info(
                f"Checking {timedelta(seconds=int(next_t))}: "
                + f"{'BREAK' if is_br_next else 'PRESENTATION'} "
                + f"(score: {score:.3f}, ref: {break_type + 1 if break_type >= 0 else 'N/A'})"
            )

            logger.info(f"Found potential start of presentation around {timedelta(seconds=int(next_t))}")
            presentation_start, start_break_type = self.binary_search_transition(cap, prev_t, next_t, False)

            logger.info("Searching for end of presentation...")
            end_offset = float(
                OmegaConf.select(self.cfg, "presentation_detection.end_search_after_start_sec", default=300.0)
            )
            end_search_start = presentation_start + end_offset

            sched_hi: float | None = None
            if self._use_schedule_duration_for_end_search() and expected_session:
                ds = parse_pretalx_duration_to_seconds(expected_session.get("Duration"))
                if ds and ds > 0:
                    slot = nearest_slot_minutes(ds / 60.0)
                    late_m, early_m = self._get_schedule_slack_minutes(slot)
                    sched_hi = min(video_duration, presentation_start + ds + late_m * 60.0)
                    # Earliest plausible end: D − early, but not before end_search_after_start_sec (plan).
                    earliest_from_sched = presentation_start + max(end_offset, ds - early_m * 60.0)
                    end_search_start = max(end_search_start, earliest_from_sched)
                    logger.info(
                        f"{tag}Schedule-guided end search: Duration≈{ds / 60.0:.0f} min (slot {slot} min), "
                        f"slack +{late_m:.0f}/−{early_m:.0f} min → End-Stream window "
                        f"{timedelta(seconds=int(earliest_from_sched))} … {timedelta(seconds=int(sched_hi))}"
                    )

            fr_end = self.get_frame_at_time(cap, end_search_start)
            is_break_end, score_end, break_type_end = self.is_break_screen(fr_end, "end_break")
            logger.info(
                f"Checking {timedelta(seconds=int(end_search_start))}: "
                + f"{'BREAK' if is_break_end else 'PRESENTATION'} "
                + f"(score: {score_end:.3f}, ref: {break_type_end + 1 if break_type_end >= 0 else 'N/A'})"
            )

            if is_break_end:
                lo = max(0.0, end_search_start - chunk_size)
                presentation_end, end_break_type = self.binary_search_transition(cap, lo, end_search_start, True)
            else:
                scan_end = sched_hi if sched_hi is not None else video_duration
                bracket_end = self._gallop_first_state_change(
                    cap, end_search_start, scan_end, start_is_break=False
                )
                if bracket_end is None and sched_hi is not None and sched_hi < video_duration - 1.0:
                    logger.info(
                        f"{tag}No End-Stream before schedule bound; continuing search from "
                        f"{timedelta(seconds=int(sched_hi))} to end of file"
                    )
                    bracket_end = self._gallop_first_state_change(
                        cap, sched_hi, video_duration, start_is_break=False
                    )
                if bracket_end is None:
                    refined_end = self._refine_presentation_end_if_oversized(
                        cap,
                        presentation_start,
                        video_duration,
                        video_duration,
                    )
                    if refined_end < video_duration - 1.0:
                        logger.info(
                            f"🎯 FOUND PRESENTATION: {timedelta(seconds=int(presentation_start))} → "
                            + f"{timedelta(seconds=int(refined_end))}"
                            + f" (Duration: {timedelta(seconds=int(refined_end - presentation_start))})"
                        )
                        logger.info(
                            f"Break screen types: Start={start_break_type + 1 if start_break_type >= 0 else 'Unknown'}, "
                            + "End=refined"
                        )
                        return (presentation_start, refined_end, start_break_type, -1)
                    use_ps_boundary = bool(
                        OmegaConf.select(
                            self.cfg,
                            "presentation_detection.oversized_use_presession_talk_boundary",
                            default=True,
                        )
                    )
                    if (
                        use_ps_boundary
                        and scheduled_session_count > 1
                        and closing_segment_index == 0
                        and self.break_references_start
                    ):
                        ps_cut = self._next_presession_to_talk_edge_after_first_talk(
                            cap,
                            presentation_start,
                            video_duration - 1.0,
                            want_nth_leave=min(1, scheduled_session_count - 1),
                        )
                        if ps_cut is not None and presentation_start + 30.0 < ps_cut < video_duration - 5.0:
                            logger.info(
                                f"{tag}End-Stream did not match on this recording; using Pre-Session→talk "
                                f"boundary for talk 2 start (same start_break as session openings)."
                            )
                            logger.info(
                                f"🎯 FOUND PRESENTATION: {timedelta(seconds=int(presentation_start))} → "
                                f"{timedelta(seconds=int(ps_cut))} "
                                f"(Duration: {timedelta(seconds=int(ps_cut - presentation_start))})"
                            )
                            logger.info(
                                f"Break screen types: Start={start_break_type + 1 if start_break_type >= 0 else 'Unknown'}, "
                                + "End=Pre-Session-boundary"
                            )
                            return (presentation_start, ps_cut, start_break_type, -1)
                    logger.info("Presentation continues until the end of video")
                    logger.info(
                        f"🎯 FOUND PRESENTATION: {timedelta(seconds=int(presentation_start))} → "
                        + f"END OF VIDEO (Duration: {timedelta(seconds=int(video_duration - presentation_start))})"
                    )
                    return (presentation_start, video_duration, start_break_type, -1)
                prev_e, next_e = bracket_end
                presentation_end, end_break_type = self.binary_search_transition(cap, prev_e, next_e, True)

            presentation_end = self._refine_presentation_end_if_oversized(
                cap,
                presentation_start,
                presentation_end,
                video_duration,
            )

            logger.info(
                f"🎯 FOUND PRESENTATION: {timedelta(seconds=int(presentation_start))} → "
                + f"{timedelta(seconds=int(presentation_end))}"
                + f" (Duration: {timedelta(seconds=int(presentation_end - presentation_start))})"
            )
            logger.info(
                f"Break screen types: Start={start_break_type + 1 if start_break_type >= 0 else 'Unknown'}, "
                + f"End={end_break_type + 1 if end_break_type >= 0 else 'Unknown'}"
            )

            return (
                presentation_start,
                presentation_end,
                start_break_type,
                end_break_type,
            )

        logger.info("No more presentations found")
        return None

    def _refine_presentation_end_if_oversized(
        self,
        cap: cv2.VideoCapture,
        presentation_start: float,
        presentation_end: float,
        video_duration: float,
    ) -> float:
        """
        If the primary search merged multiple talks, the segment can exceed max talk length.
        Grid-scan for the first presentation→End-Stream transition.

        Talks can run longer than the nominal slot (e.g. 90 min row but ~115 min on tape); the first
        End-Stream may appear *after* ``max_presentation_duration_min`` from talk start. We therefore
        scan the **entire** oversized segment up to ``presentation_end``, not only the first
        ``max_presentation_duration_min`` minutes. Schedule caps apply to the *gallop* search above;
        they are not used to clip this recovery grid (otherwise we miss End-Stream and never split
        into the next session).
        """
        max_min = float(
            OmegaConf.select(self.cfg, "presentation_detection.max_presentation_duration_min", default=90.0)
        )
        if max_min <= 0:
            return presentation_end
        max_sec = max_min * 60.0
        if presentation_end - presentation_start <= max_sec:
            return presentation_end

        end_offset = float(
            OmegaConf.select(self.cfg, "presentation_detection.end_search_after_start_sec", default=300.0)
        )
        step = float(
            OmegaConf.select(self.cfg, "presentation_detection.oversized_segment_scan_step_sec", default=45.0)
        )
        step = max(15.0, min(step, 120.0))
        min_interval = float(self.cfg.presentation_detection.min_interval)
        tag = self._tag()

        scan_lo = presentation_start + end_offset
        scan_hi = min(presentation_end, video_duration)
        if scan_hi <= scan_lo + min_interval:
            return presentation_end

        logger.info(
            f"{tag}Segment {timedelta(seconds=int(presentation_start))} → "
            f"{timedelta(seconds=int(presentation_end))} is longer than {max_min:.0f} min; "
            f"grid-scanning for first End-Stream over "
            f"{timedelta(seconds=int(scan_lo))} … {timedelta(seconds=int(scan_hi))} (step {step:.0f}s)..."
        )

        relax_list = OmegaConf.select(
            self.cfg,
            "presentation_detection.oversized_end_break_relax_deltas",
            default=None,
        )
        if relax_list is None:
            relax_list = [0.0, 0.06, 0.1, 0.14]
        elif isinstance(relax_list, (int, float)):
            relax_list = [float(relax_list)]
        else:
            relax_list = [float(x) for x in list(relax_list)]

        for relax in relax_list:
            t = scan_lo
            prev_fr = self.get_frame_at_time(cap, t)
            prev_br = self.is_break_screen(prev_fr, "end_break", threshold_relax=relax)[0]
            t += step
            while t < scan_hi:
                fr = self.get_frame_at_time(cap, t)
                is_br = self.is_break_screen(fr, "end_break", threshold_relax=relax)[0]
                if not prev_br and is_br:
                    lo = max(presentation_start, t - step)
                    hi = min(t, video_duration)
                    refined_end, _ = self.binary_search_transition(
                        cap, lo, hi, True, threshold_relax=relax
                    )
                    logger.info(
                        f"{tag}Refined talk end to {timedelta(seconds=int(refined_end))} "
                        f"(duration {timedelta(seconds=int(refined_end - presentation_start))}"
                        f"{f', end_break_relax={relax:.2f}' if relax > 0 else ''})"
                    )
                    return refined_end
                prev_br = is_br
                t += step

        logger.info(
            f"{tag}No End-Stream transition in oversized segment (grid step {step:.0f}s, "
            f"relax passes {relax_list}); keeping detector end — set break_detection.end_threshold "
            f"or add presentation_detection.oversized_end_break_relax_deltas."
        )
        return presentation_end

    def _next_presession_to_talk_edge_after_first_talk(
        self,
        cap: cv2.VideoCapture,
        presentation_start: float,
        scan_to: float,
        *,
        want_nth_leave: int = 1,
    ) -> float | None:
        """
        After talk one content has started, find ``start_break`` transitions (Pre-Session → talk).

        Short glitches can produce a false first edge; when the schedule has *S* sessions, the start of
        talk *S* for this file is often the *(S−1)*-th leave after the opening (e.g. for 2 sessions,
        use the **second** leave in this scan, not the first).
        Uses a **dense** time step so brief Pre-Session slides are not skipped.
        """
        if not self.break_references_start:
            return None
        end_off = float(
            OmegaConf.select(self.cfg, "presentation_detection.end_search_after_start_sec", default=300.0)
        )
        edge_step = float(
            OmegaConf.select(
                self.cfg,
                "presentation_detection.presession_boundary_scan_step_sec",
                default=5.0,
            )
        )
        edge_step = max(2.0, min(edge_step, 15.0))
        scan_from = float(presentation_start) + end_off
        scan_to = float(scan_to)
        if scan_to <= scan_from + edge_step:
            return None
        min_accept_t = float(presentation_start) + 15.0 * 60.0
        tag = self._tag()
        want_nth_leave = max(0, int(want_nth_leave))

        t0 = self.get_frame_at_time(cap, scan_from)
        prev_pre, _, _ = self.is_break_screen(t0, "start_break")
        t = scan_from + edge_step
        hits: list[float] = []
        while t <= scan_to:
            fr = self.get_frame_at_time(cap, t)
            cur_pre, _, _ = self.is_break_screen(fr, "start_break")
            if prev_pre and not cur_pre and t >= min_accept_t:
                lo = max(scan_from, t - edge_step)
                hi = min(t, scan_to)
                refined, _ = self.binary_search_transition(cap, lo, hi, False)
                if refined >= min_accept_t:
                    hits.append(refined)
                    logger.info(
                        f"{tag}Pre-Session→talk candidate #{len(hits)} at {timedelta(seconds=int(refined))}"
                    )
            prev_pre = cur_pre
            t += edge_step

        if not hits:
            return None
        idx = want_nth_leave if want_nth_leave < len(hits) else len(hits) - 1
        chosen = hits[idx]
        logger.info(
            f"{tag}Using Pre-Session→talk boundary #{idx + 1} of {len(hits)} "
            f"→ {timedelta(seconds=int(chosen))}"
        )
        return chosen

    def _validate_detected_presentation_durations(
        self, presentations: list[tuple[float, float]], plan: dict | None = None
    ) -> None:
        """Log warnings when segment lengths disagree with schedule or configured slot lengths."""
        rows = (plan or {}).get("presentations") or []
        for i, (start, end) in enumerate(presentations):
            dur_min = (end - start) / 60.0
            ds = parse_pretalx_duration_to_seconds(rows[i].get("Duration")) if i < len(rows) else None
            if i < len(rows) and self._use_schedule_duration_for_end_search() and ds and ds > 0:
                slot = nearest_slot_minutes(ds / 60.0)
                late_m, early_m = self._get_schedule_slack_minutes(slot)
                exp_min = ds / 60.0
                if dur_min > exp_min + late_m + 0.05 or dur_min < exp_min - early_m - 0.05:
                    logger.warning(
                        f"Presentation {i + 1}: detected {dur_min:.1f} min vs scheduled ~{exp_min:.1f} min "
                        f"(slot {slot} min: allowed +{late_m:.0f}/−{early_m:.0f} min) — check cuts or CSV Duration."
                    )

        raw = OmegaConf.select(self.cfg, "presentation_detection.expected_talk_lengths_min", default=None)
        if not raw:
            return
        slots = [float(x) for x in list(raw)]
        if not slots:
            return
        tol = float(
            OmegaConf.select(self.cfg, "presentation_detection.duration_validation_tolerance_min", default=7.0)
        )
        max_cap = float(
            OmegaConf.select(self.cfg, "presentation_detection.max_presentation_duration_min", default=0.0)
        )
        for i, (start, end) in enumerate(presentations):
            dur_min = (end - start) / 60.0
            if max_cap > 0 and dur_min > max_cap + 2.0:
                logger.warning(
                    f"Presentation {i + 1}: duration {dur_min:.1f} min still exceeds "
                    f"max_presentation_duration_min ({max_cap:.0f} min) — grid refine missed End-Stream; "
                    f"lower break_detection.threshold or oversized_segment_scan_step_sec."
                )
            gap = duration_nearest_slot_gap_min(end - start, slots)
            if gap > tol:
                logger.warning(
                    f"Presentation {i + 1}: detected duration {dur_min:.1f} min is {gap:.1f} min from the "
                    f"nearest expected slot {slots} (tolerance {tol:.1f} min). Review cuts or thresholds."
                )

    def detect_all_presentations(self, plan: dict) -> list[tuple[float, float]]:  # noqa: PLR0915
        """
        Detect all presentations in the video using binary search approach
        """
        # Start timing
        start_time = time.time()
        self._stats_frame_reads = 0
        self._stats_compare_calls = 0

        video_name = Path(plan["input_video"]).name
        self._current_video = video_name

        # Load video
        try:
            cap, fps, total_frames, duration = self.load_video(plan["input_video"])
        except Exception as e:
            logger.info(f"Error loading video: {str(e)}")
            self._last_detected_video_duration_sec = 0.0
            return []

        scan_dur = float(self._video_duration_scan)
        self._last_detected_video_duration_sec = scan_dur

        # Try to load provided break images first (room-filtered when mapping/config provides room names)
        break_images_dir = self.cfg.break_detection.images_dir
        self.break_references = self.load_break_images(break_images_dir, video_path=plan["input_video"])

        # If no break images provided or found, and auto-detect is enabled, detect them automatically
        if not self.break_references and self.cfg.break_detection.auto_detect:
            logger.info("No pre-defined break images found. Auto-detecting break screens...")
            self.break_references = self.detect_break_screens(cap, fps, duration)
            self.break_references_end = list(self.break_references)

        # Stop if no break screens found
        if not self.break_references:
            logger.info("Error: No break screens detected or provided. Cannot continue.")
            cap.release()
            self._last_detected_video_duration_sec = scan_dur
            return []

        self._refresh_break_detection_refs()

        # Find all presentations
        presentations = []
        current_time = 0

        pres_rows: list[dict] = list(plan.get("presentations") or [])

        while True:
            row = pres_rows[len(presentations)] if len(presentations) < len(pres_rows) else None
            result = self.find_next_presentation(
                cap,
                current_time,
                scan_dur,
                expected_session=row,
                scheduled_session_count=len(pres_rows),
                closing_segment_index=len(presentations),
            )

            if result is None:
                break

            start_time_sec, end_time_sec, _, _ = result
            presentations.append((start_time_sec, end_time_sec))

            # Move past this presentation for next search
            current_time = end_time_sec

            # Show overall progress
            progress = (current_time / duration) * 100
            logger.info(f"Overall progress: {progress:.1f}% of video processed")
            logger.info(f"Found {len(presentations)} presentations so far")

        cap.release()

        self._validate_detected_presentation_durations(presentations, plan)

        # logger.info summary
        end_time = time.time()
        processing_time = end_time - start_time

        logger.info(f"ANALYSIS COMPLETE: Found {len(presentations)} presentations")
        logger.info(f"Processing time: {processing_time:.1f} seconds")
        logger.info(
            f"Detection stats: frame_reads={self._stats_frame_reads}, compare_frames_calls={self._stats_compare_calls}"
        )

        for i, (start, end) in enumerate(presentations):
            start_str = str(timedelta(seconds=int(start)))
            end_str = str(timedelta(seconds=int(end)))
            duration_str = str(timedelta(seconds=int(end - start)))
            logger.info(f"Presentation {i + 1}: {start_str} → {end_str} (Duration: {duration_str})")

        # Save results to file
        with open(self.video_output_folder / plan["output_folder"] / "presentations.txt", "w") as f:
            f.write(f"Video: {plan['input_video']}\n")
            f.write(f"Total presentations: {len(presentations)}\n")
            f.write(f"Analysis time: {processing_time:.1f} seconds\n\n")

            for i, (start, end) in enumerate(presentations):
                start_str = str(timedelta(seconds=int(start)))
                end_str = str(timedelta(seconds=int(end)))
                duration_str = str(timedelta(seconds=int(end - start)))
                f.write(f"Presentation {i + 1}: {start_str} → {end_str} (Duration: {duration_str})\n")

        return presentations

    def probe_break_scores(
        self,
        video_path: str,
        times_sec: list[float] | None = None,
        grid_step_sec: float | None = None,
        save_frames_dir: Path | None = None,
    ) -> None:
        """Print is_break, score, and best ref at timestamps — use to tune break_detection.threshold."""
        cap, fps, total_frames, duration = self.load_video(video_path)
        try:
            break_dir = self.cfg.break_detection.images_dir
            self.break_references = self.load_break_images(break_dir, video_path=video_path)
            if not self.break_references and self.cfg.break_detection.auto_detect:
                logger.info("No break images; auto-detecting break screens for probe...")
                self.break_references = self.detect_break_screens(cap, fps, duration)
                self.break_references_end = list(self.break_references)
            if not self.break_references:
                logger.error("No break references — set break_detection.images_dir or enable auto_detect.")
                return

            self._refresh_break_detection_refs()

            th = float(self.cfg.break_detection.threshold)
            method = str(self.cfg.break_detection.comparison_method)
            dw, dh = self._detection_size_wh()
            room_note = ""
            if bool(OmegaConf.select(self.cfg.break_detection, "filter_refs_by_room", default=True)):
                tok = self._room_token_from_video_path(video_path)
                room_note = f" room_filter={tok!r}" if tok else " room_filter=none"
            logger.info(
                f"Probe: threshold={th} method={method} detection_size={dw}x{dh} "
                f"detection_resize={self._use_detection_resize()}{room_note}"
            )

            if times_sec is None:
                step = float(grid_step_sec) if grid_step_sec is not None else float(
                    self.cfg.presentation_detection.chunk_size
                )
                times_sec = [float(t) for t in np.arange(0.0, duration, step)]

            out_dir: Path | None = None
            if save_frames_dir is not None:
                out_dir = Path(save_frames_dir).resolve()
                out_dir.mkdir(parents=True, exist_ok=True)

            stem = Path(video_path).stem
            for t in times_sec:
                if t < 0 or t > duration:
                    continue
                fr = self.get_frame_at_time(cap, t)
                is_br, score, best = self.is_break_screen(fr, "any_break")
                ref_label = best + 1 if best >= 0 else "N/A"
                flag = "BREAK" if is_br else "presentation"
                logger.info(
                    f"  t={str(timedelta(seconds=int(t)))} score={score:.4f} best_ref={ref_label} → {flag}"
                )
                if out_dir is not None and fr is not None:
                    fp = out_dir / f"{stem}_{int(t)}s.jpg"
                    cv2.imwrite(str(fp), fr)
                    logger.info(f"    saved frame → {fp}")
        finally:
            cap.release()

    def extract_presentations(  # noqa: PLR0912
        self,
        plan: dict,
    ) -> None:
        """Extract the detected presentations as separate video files and optionally as MP3 audio"""

        if not plan["presentations"]:
            logger.info("No presentations to extract")
            return

        dq = plan.get("detection_quality") or {}
        if dq.get("passed") is False:
            logger.error(
                f"Refusing FFmpeg extract for {plan.get('input_video')}: detection_quality.passed is false. "
                f"Reasons: {dq.get('failure_reasons', [])}"
            )
            return

        idx_check = plan.get("presentations_index")
        if not idx_check:
            logger.error(f"Refusing FFmpeg extract for {plan.get('input_video')}: no presentations_index.")
            return

        logger.info("Extracting presentations...")

        output_folder = self.video_output_folder / plan["output_folder"]
        output_folder.mkdir(parents=True, exist_ok=True)

        # FIXME: replace with sequential filenames, needs to be fixed in preprocessing
        plan["presentations"] = sorted(plan["presentations"], key=lambda x: x["Start (time)"])
        for i, p in enumerate(plan["presentations"]):
            plan["presentations"][i]["Sequential_Filename"] = f"{i + 1:03d}{p['Sequential_Filename'][4:]}"
        cuts = len(plan["presentations_index"]) - len(plan["presentations"])
        if cuts > 0:
            logger.info(
                f"Warning: {cuts} more presentations detected than expected. Extracting all detected presentations."
            )
            for i in range(len(plan["presentations"]), len(plan["presentations_index"])):
                plan["presentations"].append(
                    {"Sequential_Filename": f"{i + 1:03d}_{plan['input_video'].split('/')[-1]}"}
                )

        for i, (start, end) in enumerate(plan["presentations_index"]):
            presentation = plan["presentations"][i]
            output_video = output_folder / presentation["Sequential_Filename"]
            output_audio = output_video.with_suffix(".mp3")

            if output_video.exists():
                logger.info(f"Video already exists: {output_video}, skipping...")
                continue

            # Duration in seconds
            duration = end - start

            logger.info(f"Extracting presentation {i + 1} video...")
            fast_seek = bool(OmegaConf.select(self.cfg.output, "fast_input_seek", default=False))
            if fast_seek:
                video_cmd = [
                    "ffmpeg",
                    "-ss",
                    str(int(start)),
                    "-i",
                    plan["input_video"],
                    "-t",
                    str(int(duration)),
                    "-c",
                    "copy",
                    str(output_video),
                ]
            else:
                video_cmd = [
                    "ffmpeg",
                    "-i",
                    plan["input_video"],
                    "-ss",
                    str(int(start)),
                    "-t",
                    str(int(duration)),
                    "-c",
                    "copy",
                    str(output_video),
                ]
            logger.info(f"Command: {' '.join(video_cmd)}")
            result = subprocess.run(video_cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                logger.error(f"FFmpeg error: {result.stderr}")
            else:
                logger.info(f"✅ Extracted video: {output_video}")

            # Extract audio if configured
            if self.cfg.output.extract_audio:
                audio_cmd = [
                    "ffmpeg",
                    "-i",
                    output_video,
                    "-vn",
                    "-ar",
                    "44100",
                    "-ac",
                    "2",
                    "-ab",
                    "192k",
                    "-f",
                    "mp3",
                    output_audio,
                ]
                logger.info(f"Extracting audio for presentation {i + 1}...")
                logger.info(f"Command: {' '.join(audio_cmd)}")
                result = subprocess.run(audio_cmd, capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    logger.error(f"FFmpeg audio error: {result.stderr}")
                else:
                    logger.info(f"✅ Extracted audio: {output_audio}")

    def _load_mapping_data(self):
        """Load the session->recording mapping Parquet from disk.

        The path is read from `input.mapping_file`. Missing or empty values
        raise immediately — downstream code can't pair sessions to video
        segments without this, and silently continuing produced confusing
        'No videos to process' no-ops.
        """
        if bool(OmegaConf.select(self.cfg.input, "allow_missing_mapping", default=False)):
            self.mapping_data = None
            logger.info("input.allow_missing_mapping: skipping Parquet load (probe / tooling only)")
            return

        mapping_file = self.cfg.input.mapping_file
        if not mapping_file:
            raise ValueError(
                "input.mapping_file is not set in src/video_processor/config.yaml. "
                "Run Stage 2 (process_talk_list.py) first, then point this key at the "
                "*_processed.parquet it produced."
            )
        mapping_path = Path(mapping_file)
        if not mapping_path.exists():
            raise FileNotFoundError(
                f"input.mapping_file points to a missing Parquet: {mapping_path}. "
                "Run Stage 2 (process_talk_list.py) to generate it, or fix the path."
            )
        self.mapping_data = pl.read_parquet(mapping_path)
        logger.info(f"Loaded mapping data from {mapping_path}")

    def get_output_folder(self, video_path: Path) -> str | None:
        """Get the output folder for a given video path from the Excel mapping"""
        if self.mapping_data is None:
            return None

        try:
            # Get output folder from mapping data
            output_folder = self.mapping_data.filter(pl.col("Recording") == Path(video_path).name)
            if output_folder is not None and len(output_folder) > 0:
                # Get the Output_Folder column value
                return output_folder.select("Output_Folder").unique().item()
            return None

        except Exception as e:
            logger.info(f"Warning: Could not get output folder: {e}")
            return None

    def save_presentation_metadata(self, plan: dict, presentations: list[tuple[float, float]]) -> None:
        """Save presentation metadata in a JSON file for future reference"""
        metadata_file = self.video_output_folder / plan["output_folder"] / "metadata.json"
        metadata = {"video": plan, "presentations_index": []}

        for i, (start, end) in enumerate(presentations):
            metadata["presentations_index"].append(
                {
                    "index": i + 1,
                    "start_seconds": int(start),
                    "end_seconds": int(end),
                    "duration_seconds": int(end - start),
                    "start_timecode": str(timedelta(seconds=int(start))),
                    "end_timecode": str(timedelta(seconds=int(end))),
                    "duration": str(timedelta(seconds=int(end - start))),
                }
            )

        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"Saved presentation metadata to {metadata_file}")

    def make_processing_plan(self):
        # Generate processing plan
        logger.info("Generating processing plan...")
        processing_plan = self.generate_processing_plan()
        if not processing_plan:
            logger.info("No videos to process")
            return

        # Process each video according to plan
        logger.info(f"Starting batch processing of {len(processing_plan)} videos...")
        results = []

        for i, plan in enumerate(processing_plan):
            logger.info(f"Processing video {i + 1}/{len(processing_plan)}: {plan['input_video']}")
            success = self.process_video(plan)
            plan["success"] = success
            results.append(plan)

        # Persist success (process_video's update_processing_plan ran before success was set).
        with self.processing_plan_path.open("w") as f:
            f.write("# Generated by presentation_detector.py — do not hand-edit while a run is in progress.\n\n")
            yaml.safe_dump(
                results, f, sort_keys=False, allow_unicode=True, default_flow_style=False
            )

        logger.info(f"BATCH PROCESSING COMPLETE - {len(processing_plan)} videos")

        success_count = sum(1 for p in results if p.get("success"))
        fail_count = len(results) - success_count

        logger.info(f"Successfully processed: {success_count}")
        logger.info(f"Failed: {fail_count}")

        logger.info("=== DETECTION BATCH SUMMARY (tabular) ===\n" + _format_detection_batch_table(results))

        logger.info(
            "=== DETECTION BATCH DETAIL "
            "(sessions expected | segments found | sessions missed | surplus | quality) ==="
        )
        for p in results:
            sr = p.get("session_report")
            if not sr:
                logger.info(f"  {Path(p.get('input_video', '')).name}: (no session_report)")
                continue
            q = "OK" if sr.get("quality_passed") else "FAIL"
            logger.info(
                f"  {sr['file']}: expected={sr['sessions_expected']} "
                f"found={sr['segments_found']} missed={sr['sessions_missed']} "
                f"surplus={sr['segments_surplus_vs_schedule']} quality={q}"
            )

        batch_reports = [p["session_report"] for p in results if p.get("session_report")]
        if batch_reports:
            batch_path = self.video_output_folder / "detection_batch_report.json"
            with batch_path.open("w", encoding="utf-8") as f:
                json.dump(batch_reports, f, indent=2, ensure_ascii=False)
            logger.info(f"Wrote per-file session reports to {batch_path}")
            logger.info(
                f"Appended per-video lines to {self.video_output_folder / 'detection_session_report.jsonl'} "
                "(JSONL; safe to delete to reset)"
            )

        if fail_count > 0:
            logger.info("Failed videos:")
            for p in results:
                if not p.get("success"):
                    logger.info(f"  - {p.get('input_video')}")


_DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"


def _format_detection_batch_table(results: list[dict]) -> str:
    """ASCII table: file, expected sessions, segments found, count OK, quality PASS/FAIL."""
    file_w = 46
    lines: list[str] = []
    header = (
        f"{'File':<{file_w}}  {'Exp':>4}  {'Found':>5}  {'Count':^10}  {'Quality':>7}"
    )
    rule = "-" * len(header)
    lines.append(header)
    lines.append(rule)
    pass_n = 0
    fail_n = 0
    na_quality = 0
    for p in results:
        sr = p.get("session_report") or {}
        fn = Path(p.get("input_video", "")).name
        if len(fn) > file_w:
            fn = fn[: file_w - 1] + "…"
        exp = sr.get("sessions_expected")
        found = sr.get("segments_found")
        exp_s = "—" if exp is None else str(int(exp))
        found_s = "—" if found is None else str(int(found))
        if isinstance(exp, int) and isinstance(found, int):
            count_s = "OK" if exp == found else "MISMATCH"
        else:
            count_s = "—"
        qp = sr.get("quality_passed")
        if qp is True:
            q_s = "PASS"
            pass_n += 1
        elif qp is False:
            q_s = "FAIL"
            fail_n += 1
        else:
            q_s = "—"
            na_quality += 1
        lines.append(
            f"{fn:<{file_w}}  {exp_s:>4}  {found_s:>5}  {count_s:^10}  {q_s:>7}"
        )
    lines.append(rule)
    n = len(results)
    tail = f"Summary: {n} file(s)  |  quality PASS={pass_n}  FAIL={fail_n}"
    if na_quality:
        tail += f"  (no quality row: {na_quality})"
    lines.append(tail)
    return "\n".join(lines)


def _parse_probe_times(s: str | None) -> list[float] | None:
    if not s or not str(s).strip():
        return None
    return [float(x.strip()) for x in str(s).split(",") if x.strip()]


def main():  # noqa: PLR0912, PLR0915
    """Main function with command line interface"""
    parser = argparse.ArgumentParser(description="Process conference videos")
    parser.add_argument(
        "--config",
        default=str(_DEFAULT_CONFIG_PATH),
        help=f"Path to configuration file (default: {_DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--output",
        help="Output folder for extracted presentations (overrides config)",
    )
    parser.add_argument(
        "--break-images",
        help="Directory containing break screen images (overrides config)",
    )
    parser.add_argument(
        "--extract",
        action="store_true",
        help="Extract presentations as separate files (override config)",
    )
    parser.add_argument(
        "--audio",
        "-a",
        action="store_true",
        help="Extract audio from presentations as MP3 (override config)",
    )
    parser.add_argument("--input-folder", "-i", help="Process all videos in the specified folder")
    parser.add_argument(
        "--video",
        metavar="PATH",
        help="Process only this video file (sets input.video_path; use with --detect-only to validate one file)",
    )
    parser.add_argument(
        "--fail-on-detect-mismatch",
        action="store_true",
        help="With --detect-only, exit with code 1 if any video fails detection_quality or process_video",
    )
    parser.add_argument(
        "--probe-video",
        metavar="PATH",
        help="Log break scores vs references at timestamps, then exit (tune threshold)",
    )
    parser.add_argument(
        "--probe-times",
        metavar="SEC_LIST",
        help="Comma-separated times in seconds (e.g. 0,300,900). Default: grid from --probe-every or chunk_size",
    )
    parser.add_argument(
        "--probe-every",
        type=float,
        metavar="SEC",
        help="Sample every SEC seconds from 0 to end of file (overrides --probe-times if set)",
    )
    parser.add_argument(
        "--probe-save-frames",
        metavar="DIR",
        help="Save full-resolution JPEGs at each probe timestamp",
    )
    parser.add_argument(
        "--probe-skip-mapping",
        action="store_true",
        help="Do not load input.mapping_file Parquet (for probe without session mapping)",
    )
    parser.add_argument(
        "--detect-only",
        action="store_true",
        help="Run session mapping + detection only; write processing_plan.yaml with detection_quality (no FFmpeg).",
    )
    parser.add_argument(
        "--extract-only",
        action="store_true",
        help="FFmpeg extract only from existing processing_plan.yaml (requires prior successful detection).",
    )

    args = parser.parse_args()

    # Load configuration
    config_path = Path(args.config)
    if not config_path.exists():
        logger.info(f"Config file not found: {args.config}")
        logger.info("Creating default config file...")
        default_cfg = OmegaConf.create(
            {
                "input": {
                    "video_path": "",
                    "folder": "",
                    "extensions": "mp4,mkv,avi,mov,webm",
                    "mapping_file": "",
                    "allow_missing_mapping": False,
                },
                "video": {
                    "enable_resize": False,
                    "processing_size": [320, 180],
                    "detection_resize": True,
                    "detection_size": [640, 360],
                    "seek_use_pos_msec": False,
                },
                "break_detection": {
                    "images_dir": "",
                    "threshold": 0.38,
                    "comparison_method": "template",
                    "auto_detect": True,
                    "detected_screens_dir": "detected_break_screens",
                    "filter_refs_by_room": True,
                    "shared_ref_substrings": ["All-Rooms", "Pre-Session-Graphic-All-Rooms"],
                    "room_names": [],
                    "start_ref_substrings": ["Pre-Session-Graphic-All-Rooms"],
                    "end_ref_substrings": ["End-Stream"],
                },
                "presentation_detection": {
                    "min_interval": 5,
                    "chunk_size": 300,
                    "gallop_max_step": 3600,
                    "end_search_after_start_sec": 300,
                    "use_schedule_duration_for_end_search": True,
                    "sampling_interval": 30,
                    "max_samples": 200,
                    "cluster_threshold": 0.90,
                    "expected_talk_lengths_min": [30, 45, 60, 90],
                    "duration_validation_tolerance_min": 7,
                    "max_presentation_duration_min": 90,
                    "oversized_segment_scan_step_sec": 120,
                    "detection_quality": {
                        "enabled": True,
                        "fail_on_count_mismatch": True,
                        "max_segment_duration_min": 120,
                        "fail_single_segment_max_video_fraction": 0.72,
                    },
                },
                "output": {
                    "folder": "extracted_presentations",
                    "extract_presentations": False,
                    "extract_audio": True,
                    "save_metadata": True,
                    "fast_input_seek": False,
                    "auto_detect_on_extract": False,
                },
                "event": {
                    "lunch_break_cut": 13,
                },
            }
        )
        OmegaConf.save(default_cfg, args.config)

    # Load the configuration
    cfg = OmegaConf.load(args.config)

    if args.probe_skip_mapping:
        cfg = OmegaConf.merge(cfg, OmegaConf.create({"input": {"allow_missing_mapping": True}}))

    # Override with command line arguments if provided
    if args.output:
        cfg.output.folder = args.output
    if args.break_images:
        cfg.break_detection.images_dir = args.break_images
    if args.extract:
        cfg.output.extract_presentations = True
    if args.audio:
        cfg.output.extract_audio = True
    if args.input_folder:
        cfg.input.folder = args.input_folder
    if args.video:
        cfg.input.video_path = str(Path(args.video).expanduser().resolve())

    # Initialize detector
    detector = VideoPresenterDetector(cfg)

    if args.extract_only and args.detect_only:
        logger.error("Use only one of --extract-only or --detect-only.")
        return

    if args.extract_only:
        detector.extract_presentations_from_plan(extract_only=True)
        return

    if args.detect_only:
        detector.make_processing_plan()
        if args.fail_on_detect_mismatch:
            detector.load_processing_plan()
            bad = [
                p
                for p in detector.processing_plan
                if p.get("presentations")
                and (
                    not p.get("success")
                    or not (p.get("detection_quality") or {}).get("passed", False)
                )
            ]
            if bad:
                for p in bad:
                    logger.error(f"Detect mismatch / quality fail: {p.get('input_video')}")
                raise SystemExit(1)
        return

    if args.probe_video:
        times = _parse_probe_times(args.probe_times)
        save_dir = Path(args.probe_save_frames) if args.probe_save_frames else None
        if args.probe_every is not None:
            detector.probe_break_scores(
                args.probe_video,
                times_sec=None,
                grid_step_sec=float(args.probe_every),
                save_frames_dir=save_dir,
            )
        elif times is not None:
            detector.probe_break_scores(
                args.probe_video,
                times_sec=times,
                grid_step_sec=None,
                save_frames_dir=save_dir,
            )
        else:
            detector.probe_break_scores(
                args.probe_video,
                times_sec=None,
                grid_step_sec=float(cfg.presentation_detection.chunk_size),
                save_frames_dir=save_dir,
            )
        return

    if cfg.output.make_processing_plan:
        detector.make_processing_plan()

    if cfg.output.extract_presentations:
        logger.info("Starting extraction of presentations (from processing_plan.yaml)...")
        detector.extract_presentations_from_plan(extract_only=False)


if __name__ == "__main__":
    main()
