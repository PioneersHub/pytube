"""
Video Presentation Detector - Automatically detects and extracts presentations
from conference or livestream recordings by finding transitions between
break screens and presentations.

Supports batch processing of multiple videos from an input folder.
"""

import argparse
import glob
import json
import subprocess
import time
import traceback
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import cv2
import numpy as np
import polars as pl
from omegaconf import DictConfig, OmegaConf

from manager import logger


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

    # Parse extensions
    ext_list = [ext.strip() for ext in extensions.split(",")]

    # Get all matching files
    video_files = []
    for ext in ext_list:
        # Make sure extension has dot prefix
        if not ext.startswith("."):
            ext = f".{ext}"

        pattern = str(input_path / f"*{ext}")
        video_files.extend(glob.glob(pattern))

        # Also try uppercase extension
        pattern = str(input_path / f"*{ext.upper()}")
        video_files.extend(glob.glob(pattern))

    # Sort files for consistent processing order
    video_files.sort()

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
        self.processing_plan_path = self.video_output_folder / "processing_plan.json"
        self.processing_plan = []

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
        video_files = []
        ext_list = extensions.split(",")
        for ext in ext_list:
            video_files.extend(folder.glob(f"*{ext}"))

        # Sort files for consistent processing order
        video_files.sort()

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

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps

        logger.info(f"Video loaded: {video_path}")
        logger.info(f"Duration: {timedelta(seconds=int(duration))}, FPS: {fps}")
        logger.info(f"Total frames: {total_frames}")

        return cap, fps, total_frames, duration

    def generate_processing_plan(self) -> list[dict]:
        """
        Generate a processing plan for all videos based on the mapping file

        Returns:
            List of dictionaries containing processing information for each video
        """
        try:
            # Load mapping data
            self._load_mapping_data()
            if self.mapping_data is None:
                logger.info("No mapping data available")
                return []

            # Get list of video files
            input_folder = Path(self.cfg.input.folder)
            video_files = self.get_video_files(input_folder, self.cfg.input.extensions)
            if not video_files:
                logger.info("No video files found")
                return []

            # Generate processing plan
            processing_plan = []
            for video_path in video_files:
                video_name = video_path.name

                # Get output folder from mapping
                output_folder = self.get_output_folder(video_path)
                if not output_folder:
                    logger.info(f"No output folder found for {video_name}")
                    continue

                presentations = (
                    self.mapping_data.filter(pl.col("Recording") == Path(video_path).name)
                    .sort("Start (time)")
                    .to_dicts()
                )

                # Create plan entry
                plan_entry = {
                    "input_video": str(video_path),
                    "output_folder": str(output_folder),
                    "presentations": presentations,
                }
                processing_plan.append(plan_entry)

            # Save processing plan to JSON
            with open(self.processing_plan_path, "w") as f:
                json.dump(processing_plan, f, indent=2)
            logger.info(f"Saved processing plan to {self.processing_plan_path}")

            return processing_plan

        except Exception as e:
            logger.info(f"Error generating processing plan: {str(e)}")
            traceback.print_exc()
            return []

    def load_processing_plan(self) -> list[dict]:
        """Load the processing plan from JSON"""
        try:
            with open(self.processing_plan_path) as f:
                self.processing_plan = json.load(f)
            return self.processing_plan
        except Exception as e:
            logger.info(f"Error loading processing plan: {str(e)}")
            traceback.print_exc()
            return []

    def update_processing_plan(self, plan: dict) -> None:
        """
        Update the processing plan with new information

        Args:
            plan: Dictionary containing updated processing information
        """
        try:
            processing_plan = self.load_processing_plan()
            for i, p in enumerate(processing_plan):
                if p["input_video"] == plan["input_video"]:
                    processing_plan[i] = plan
                    break
            with open(self.processing_plan_path, "w") as f:
                json.dump(processing_plan, f, indent=2)
        except Exception as e:
            logger.info(f"Error updating processing plan: {str(e)}")
            traceback.print_exc()

    def extract_presentations_from_plan(self) -> None:
        """Extract clips using the processing plan.

        Reads `processing_plan.json` from disk and runs FFmpeg extraction for each
        video's detected segments. When the plan file is missing, runs detection
        first so a cold-start `--extract` is a full pipeline run. Set
        `make_processing_plan: true` + `extract_presentations: false` in the
        config for an inspect-before-cut dry run.
        """
        if not self.processing_plan_path.exists():
            logger.info(f"No processing plan at {self.processing_plan_path} — running detection first.")
            self.make_processing_plan()

        try:
            self.load_processing_plan()
            for plan in self.processing_plan:
                if not plan["presentations"]:
                    continue

                logger.info(f"Extracting presentations from {plan['input_video']}...")
                self.extract_presentations(plan)

        except Exception as e:
            logger.info(f"Error extracting presentations: {str(e)}")
            traceback.print_exc()

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
            logger.info(f"Found {len(presentations_index)} presentations")
            if len(presentations_index) != len(plan["presentations"]):
                logger.warning(
                    f"MISMATCH: Expected {len(plan['presentations'])} presentations, got {len(presentations_index)} indexes."
                )

            # Update processing plan with detected presentations
            plan["presentations_index"] = presentations_index
            self.update_processing_plan(plan)

            # Save metadata if configured
            if presentations_index and self.cfg.output.save_metadata:
                self.save_presentation_metadata(plan, presentations_index)
            return True

        except Exception as e:
            logger.info(f"Error processing video {plan.get('input_video')}: {str(e)}")
            import traceback

            traceback.print_exc()
            return False

    def get_frame_at_time(self, cap: cv2.VideoCapture, time_sec: float) -> np.ndarray | None:
        """Get a frame at a specific time in the video"""
        frame_pos = int(time_sec * cap.get(cv2.CAP_PROP_FPS))
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
        ret, frame = cap.read()
        if not ret:
            logger.info(f"WARNING: Could not read frame at {time_sec}s")
            return None

        # Only resize if enabled in config
        if self.cfg.video.enable_resize:
            width, height = self.cfg.video.processing_size
            return cv2.resize(frame, (width, height))

        return frame

    def load_break_images(self, break_images_dir: str) -> list[np.ndarray]:
        """Load break images from a directory"""
        if not break_images_dir:
            logger.info("No break images directory provided")
            return []

        break_images_path = Path(break_images_dir)
        if not break_images_path.is_dir():
            logger.info(f"Break images directory does not exist: {break_images_dir}")
            return []

        logger.info(f"Loading break images from {break_images_dir}...")
        image_files = (
            glob.glob(str(break_images_path / "*.jpg"))
            + glob.glob(str(break_images_path / "*.png"))
            + glob.glob(str(break_images_path / "*.jpeg"))
        )

        if not image_files:
            logger.info(f"No images found in {break_images_dir}")
            return []

        break_images = []

        for img_path in image_files:
            img = cv2.imread(img_path)
            if img is not None:
                # Only resize if enabled
                if self.cfg.video.enable_resize:
                    width, height = self.cfg.video.processing_size
                    img = cv2.resize(img, (width, height))

                break_images.append(img)
                logger.info(f"  Loaded: {Path(img_path).name}")

        logger.info(f"✅ Loaded {len(break_images)} break images")
        return break_images

    def detect_break_screens(self, cap: cv2.VideoCapture, fps: float, duration: float) -> list[np.ndarray]:
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

        for cluster_id, frame_indices in clusters.items():
            if len(frame_indices) < 3:
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

    def _estimate_cluster_duration(self, frame_indices: list[int], sample_times: list[float], interval: float) -> float:
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
        method = self.cfg.break_detection.comparison_method

        if method == "template":
            result = cv2.matchTemplate(frame1, frame2, cv2.TM_CCOEFF_NORMED)
            return np.max(result)
        elif method == "histogram":
            hist1 = cv2.calcHist([frame1], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
            hist1 = cv2.normalize(hist1, hist1).flatten()
            hist2 = cv2.calcHist([frame2], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
            hist2 = cv2.normalize(hist2, hist2).flatten()
            return cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
        else:
            raise ValueError(f"Unknown comparison method: {method}")

    def is_break_screen(self, frame: np.ndarray | None, break_references: list[np.ndarray]) -> tuple[bool, float, int]:
        """
        Check if a frame is a break screen by comparing to multiple references
        """
        threshold = self.cfg.break_detection.threshold

        if frame is None:
            return True, 1.0, -1  # Default to break if frame couldn't be read

        best_score = 0
        best_index = -1

        for i, ref in enumerate(break_references):
            similarity = self.compare_frames(frame, ref)
            if similarity > best_score:
                best_score = similarity
                best_index = i

        is_break = best_score > threshold
        return is_break, best_score, best_index

    def binary_search_transition(
        self,
        cap: cv2.VideoCapture,
        break_references: list[np.ndarray],
        start_time: float,
        end_time: float,
        target_is_break: bool,
    ) -> tuple[float, int]:
        """
        Binary search to find transition point between break and presentation
        """
        min_interval = self.cfg.presentation_detection.min_interval
        threshold = self.cfg.break_detection.threshold

        current_start = start_time
        current_end = end_time

        logger.info(f"Binary search from {timedelta(seconds=int(start_time))} to {timedelta(seconds=int(end_time))}")
        logger.info(f"Looking for {'presentation→break' if target_is_break else 'break→presentation'} transition")

        best_match_overall = -1
        iteration = 1
        while current_end - current_start > min_interval:
            mid_time = (current_start + current_end) / 2
            mid_frame = self.get_frame_at_time(cap, mid_time)

            is_break, score, best_match = self.is_break_screen(mid_frame, break_references)
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

    def find_next_presentation(
        self,
        cap: cv2.VideoCapture,
        break_references: list[np.ndarray],
        current_time: float,
        video_duration: float,
    ) -> tuple[float, float, int, int] | None:
        """
        Find the next presentation in the video
        """
        min_interval = self.cfg.presentation_detection.min_interval
        threshold = self.cfg.break_detection.threshold
        chunk_size = self.cfg.presentation_detection.chunk_size

        logger.info(f"{'=' * 80}")
        logger.info(f"Searching for next presentation starting from {timedelta(seconds=int(current_time))}")
        logger.info(f"{'=' * 80}")

        # Check if we're already at the end of the video
        if current_time >= video_duration - chunk_size / 2:
            logger.info("Reached end of video, no more presentations to find")
            return None

        # Step 1: Find the next break→presentation transition (start of presentation)
        # First do a coarse search in chunk_size intervals
        search_time = current_time
        start_frame = self.get_frame_at_time(cap, search_time)
        is_break, score, break_type = self.is_break_screen(start_frame, break_references)

        logger.info(
            f"Current position at {timedelta(seconds=int(search_time))} is "
            + f"{'BREAK' if is_break else 'PRESENTATION'} "
            + f"(score: {score:.3f}, ref: {break_type + 1 if break_type >= 0 else 'N/A'})"
        )

        # If we're already in a presentation, we need to find the next break first
        if not is_break:
            logger.info("Currently in a presentation, finding its end first...")
            while search_time < video_duration:
                search_time += chunk_size
                if search_time >= video_duration:
                    logger.info("Reached end of video during initial search")
                    return None

                search_frame = self.get_frame_at_time(cap, search_time)
                is_break, score, break_type = self.is_break_screen(search_frame, break_references)

                logger.info(
                    f"Checking {timedelta(seconds=int(search_time))}: "
                    + f"{'BREAK' if is_break else 'PRESENTATION'} "
                    + f"(score: {score:.3f}, ref: {break_type + 1 if break_type >= 0 else 'N/A'})"
                )

                if is_break:
                    logger.info(
                        f"Found potential end of current presentation around {timedelta(seconds=int(search_time))}"
                    )
                    # Now refine this with binary search
                    presentation_end, end_break_type = self.binary_search_transition(
                        cap, break_references, search_time - chunk_size, search_time, True
                    )

                    search_time = presentation_end
                    is_break = True
                    break

        # Find start of next presentation (break→presentation transition)
        if is_break:
            logger.info("Searching for start of next presentation...")
            start_break_type = break_type

            # Coarse search in chunk_size intervals
            while search_time < video_duration:
                search_time += chunk_size
                if search_time >= video_duration:
                    logger.info("Reached end of video during initial search")
                    return None

                search_frame = self.get_frame_at_time(cap, search_time)
                is_break, score, break_type = self.is_break_screen(search_frame, break_references)

                logger.info(
                    f"Checking {timedelta(seconds=int(search_time))}: "
                    + f"{'BREAK' if is_break else 'PRESENTATION'} "
                    + f"(score: {score:.3f}, ref: {break_type + 1 if break_type >= 0 else 'N/A'})"
                )

                if not is_break:
                    logger.info(f"Found potential start of presentation around {timedelta(seconds=int(search_time))}")
                    # Refine with binary search
                    presentation_start, start_break_type = self.binary_search_transition(
                        cap, break_references, search_time - chunk_size, search_time, False
                    )

                    # Step 2: Find the end of this presentation (presentation→break transition)
                    logger.info("Searching for end of presentation...")

                    # Start searching 20 minutes after the start
                    end_search_start = presentation_start + 1200  # 20 minutes in seconds

                    # Coarse search for end of presentation
                    search_time = end_search_start
                    while search_time < video_duration:
                        search_frame = self.get_frame_at_time(cap, search_time)
                        is_break, score, break_type = self.is_break_screen(search_frame, break_references)

                        logger.info(
                            f"Checking {timedelta(seconds=int(search_time))}: "
                            + f"{'BREAK' if is_break else 'PRESENTATION'} "
                            + f"(score: {score:.3f}, ref: {break_type + 1 if break_type >= 0 else 'N/A'})"
                        )

                        if is_break:
                            logger.info(
                                f"Found potential end of presentation around {timedelta(seconds=int(search_time))}"
                            )
                            # Refine with binary search
                            presentation_end, end_break_type = self.binary_search_transition(
                                cap, break_references, search_time - chunk_size, search_time, True
                            )

                            # Success! Return the presentation interval
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

                        search_time += chunk_size
                        if search_time >= video_duration:
                            # Presentation goes until the end of the video
                            logger.info("Presentation continues until the end of video")
                            logger.info(
                                f"🎯 FOUND PRESENTATION: {timedelta(seconds=int(presentation_start))} → "
                                + f"END OF VIDEO (Duration: {timedelta(seconds=int(video_duration - presentation_start))})"
                            )
                            return (presentation_start, video_duration, start_break_type, -1)

                # No presentation found in this chunk, continue searching

        logger.info("No more presentations found")
        return None

    def detect_all_presentations(self, plan: dict) -> list[tuple[float, float]]:
        """
        Detect all presentations in the video using binary search approach
        """
        # Start timing
        start_time = time.time()

        # Load video
        try:
            cap, fps, total_frames, duration = self.load_video(plan["input_video"])
        except Exception as e:
            logger.info(f"Error loading video: {str(e)}")
            return []

        # Try to load provided break images first
        break_images_dir = self.cfg.break_detection.images_dir
        self.break_references = self.load_break_images(break_images_dir)

        # If no break images provided or found, and auto-detect is enabled, detect them automatically
        if not self.break_references and self.cfg.break_detection.auto_detect:
            logger.info("No pre-defined break images found. Auto-detecting break screens...")
            self.break_references = self.detect_break_screens(cap, fps, duration)

        # Stop if no break screens found
        if not self.break_references:
            logger.info("Error: No break screens detected or provided. Cannot continue.")
            cap.release()
            return []

        # Find all presentations
        presentations = []
        current_time = 0

        while True:
            result = self.find_next_presentation(cap, self.break_references, current_time, duration)

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

        # logger.info summary
        end_time = time.time()
        processing_time = end_time - start_time

        logger.info(f"ANALYSIS COMPLETE: Found {len(presentations)} presentations")
        logger.info(f"Processing time: {processing_time:.1f} seconds")

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

    def extract_presentations(
        self,
        plan: dict,
    ) -> None:
        """Extract the detected presentations as separate video files and optionally as MP3 audio"""

        if not plan["presentations"]:
            logger.info("No presentations to extract")
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
                "Warning: {cuts} more presentations detected than expected. Extracting all detected presentations."
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
            # FFmpeg command for video extraction without re-encoding
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
                output_video,
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

        # logger.info summary
        logger.info(f"BATCH PROCESSING COMPLETE - {len(processing_plan)} videos")

        success_count = sum(1 for _, success in results if success)
        fail_count = len(results) - success_count

        logger.info(f"Successfully processed: {success_count}")
        logger.info(f"Failed: {fail_count}")

        if fail_count > 0:
            logger.info("Failed videos:")
            for video_path, success in results:
                if not success:
                    logger.info(f"  - {video_path}")


_DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"


def main():
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

    args = parser.parse_args()

    # Load configuration
    config_path = Path(args.config)
    if not config_path.exists():
        logger.info(f"Config file not found: {args.config}")
        logger.info("Creating default config file...")
        default_cfg = OmegaConf.create(
            {
                "input": {"video_path": "", "folder": "", "extensions": "mp4,mkv,avi,mov,webm"},
                "video": {"enable_resize": False, "processing_size": [320, 180]},
                "break_detection": {
                    "images_dir": "",
                    "threshold": 0.92,
                    "comparison_method": "template",
                    "auto_detect": True,
                    "detected_screens_dir": "detected_break_screens",
                },
                "presentation_detection": {
                    "min_interval": 5,
                    "chunk_size": 300,
                    "sampling_interval": 30,
                    "max_samples": 200,
                    "cluster_threshold": 0.90,
                },
                "output": {
                    "folder": "extracted_presentations",
                    "extract_presentations": False,
                    "extract_audio": True,
                    "save_metadata": True,
                },
                "event": {
                    "lunch_break_cut": 13,
                },
            }
        )
        OmegaConf.save(default_cfg, args.config)

    # Load the configuration
    cfg = OmegaConf.load(args.config)

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

    # Initialize detector
    detector = VideoPresenterDetector(cfg)

    if cfg.output.make_processing_plan:
        detector.make_processing_plan()

    # If extraction is requested, run the extraction step
    if cfg.output.extract_presentations:
        logger.info("Starting extraction of presentations...")
        detector.extract_presentations_from_plan()


if __name__ == "__main__":
    main()
