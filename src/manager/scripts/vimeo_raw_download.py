"""Stage-1 raw-stream bulk downloader for the auto-cutter pipeline.

Pulls long live-stream recordings from any number of Vimeo source accounts into
the folder `src/video_processor/presentation_detector.py` reads. Filenames are
preserved as the (sanitized) Vimeo title so that
`src/video_processor/process_talk_list.py:find_recording()` still matches.

Separate from `vimeo_download.py`, which handles the unrelated cut-video
re-download flow.
"""

import http
import json
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests
from vimeo import VimeoClient

from manager import logger

_HTTP_OK = http.HTTPStatus.OK

_ILLEGAL_FILENAME_CHARS = re.compile(r'[\\/*?"<>|:]')
_CHUNK_SIZE = 1024 * 1024  # 1 MiB — raw streams are multi-GB; 1 KiB makes this ~3x slower.
_CONNECT_TIMEOUT = 30
_READ_TIMEOUT = 120
_DEFAULT_RETRY_MAX_ATTEMPTS = 3
_BACKOFF_CAP_SECONDS = 30
# Operators move unwanted raw videos (break-slide-only recordings etc.) into this
# subdirectory of output_dir. Anything present there is permanently skipped.
_REMOVED_DIRNAME = "removed"
# Trailing "_<digits>" suffix on a filename indicates our vimeo_id disambiguation.
# Vimeo video IDs are numeric and currently 9–10 digits; require 6+ to avoid
# false positives on titles that happen to end in "_<small number>".
_TRAILING_VIMEO_ID = re.compile(r"_(\d{6,})$")


def _backoff_seconds(attempt_index: int) -> float:
    """Exponential backoff: 1s, 2s, 4s, 8s, ..., capped at _BACKOFF_CAP_SECONDS."""
    return min(2**attempt_index, _BACKOFF_CAP_SECONDS)


def load_blocklist(removed_dir: Path) -> tuple[set[str], set[str]]:
    """Scan the removed/ directory and return (vimeo_ids, titles) to skip.

    Each .mp4 in `removed_dir` blocks a video by either its sanitized title
    (base filename without `.mp4`, minus any trailing `_<vimeo_id>`) or by the
    vimeo_id extracted from that suffix. Missing directory → empty blocklist.
    """
    blocked_ids: set[str] = set()
    blocked_titles: set[str] = set()
    if not removed_dir.is_dir():
        return blocked_ids, blocked_titles

    for entry in removed_dir.glob("*.mp4"):
        stem = entry.stem  # filename without .mp4
        match = _TRAILING_VIMEO_ID.search(stem)
        if match:
            blocked_ids.add(match.group(1))
            blocked_titles.add(stem[: match.start()])
        else:
            blocked_titles.add(stem)
    return blocked_ids, blocked_titles


def make_client(account: dict[str, Any]) -> VimeoClient:
    """Build a Vimeo client for a single source account."""
    return VimeoClient(
        token=account["access_token"],
        key=account["client_id"],
        secret=account["client_secret"],
    )


def _paginate(client: VimeoClient, url: str) -> list[dict]:
    """Walk Vimeo paginated endpoints (100 per page) and return all data items."""
    items: list[dict] = []
    page = 1
    while True:
        response = client.get(url, params={"page": page, "per_page": 100})
        if response.status_code != _HTTP_OK:
            logger.error(
                "Vimeo list error",
                url=url,
                page=page,
                status=response.status_code,
                body=response.text[:500],
            )
            break
        data = response.json()
        batch = data.get("data") or []
        if not batch:
            break
        items.extend(batch)
        if not (data.get("paging") or {}).get("next"):
            break
        page += 1
    return items


def list_videos_in_folder(client: VimeoClient, user_id: str, folder_id: str) -> list[dict]:
    """Return every video in a Vimeo project/folder for the given user."""
    raw_items = _paginate(client, f"https://api.vimeo.com/users/{user_id}/projects/{folder_id}/items")
    # Folder items are wrapped: {"type": "video", "video": {...}}. Unwrap to the video dict
    # so callers see the same shape as /me/videos results.
    videos = []
    for item in raw_items:
        if item.get("type") == "video" and item.get("video"):
            videos.append(item["video"])
        elif item.get("uri", "").startswith("/videos/"):
            videos.append(item)
    return videos


def list_videos_matching(
    client: VimeoClient,
    title_contains: str | None = None,
    title_regex: str | None = None,
) -> list[dict]:
    """Return videos from /me/videos filtered by title.

    Exactly one of `title_contains` / `title_regex` must be provided (enforced by
    the config validator before we get here).
    """
    all_videos = _paginate(client, "https://api.vimeo.com/me/videos")
    if title_contains:
        needle = title_contains.lower()
        return [v for v in all_videos if needle in (v.get("name") or "").lower()]
    if title_regex:
        compiled = re.compile(title_regex)
        return [v for v in all_videos if compiled.search(v.get("name") or "")]
    return all_videos


def select_videos_for_account(
    client: VimeoClient,
    selection: dict[str, Any],
    user_id: str | None,
) -> list[dict]:
    """Dispatch on whichever selection key is set for this account."""
    if selection.get("folder_id"):
        if not user_id:
            raise ValueError("user_id required when selection.folder_id is set")
        return list_videos_in_folder(client, user_id, selection["folder_id"])
    if selection.get("title_contains"):
        return list_videos_matching(client, title_contains=selection["title_contains"])
    if selection.get("title_regex"):
        return list_videos_matching(client, title_regex=selection["title_regex"])
    raise ValueError("selection must set exactly one of folder_id, title_contains, title_regex")


def sanitize_title(name: str) -> str:
    """Strip filesystem-illegal chars and a trailing .mp4. No length cap.

    Keeps the original title shape so `process_talk_list.py:find_recording()` still
    reconstructs the exact filename (`"PyConDE & PyData 2025 - Room - Day Period.mp4"`).
    """
    cleaned = _ILLEGAL_FILENAME_CHARS.sub("_", name or "").strip()
    if cleaned.lower().endswith(".mp4"):
        cleaned = cleaned[:-4].rstrip()
    return cleaned


def _video_id(video: dict) -> str:
    uri = video.get("uri") or ""
    return uri.rsplit("/", 1)[-1] if uri else str(video.get("id") or "")


def plan_filenames(
    videos_per_account: dict[str, list[dict]],
    output_dir: Path,
) -> dict[str, Path]:
    """Compute the full {vimeo_id: target_path} rename plan up front.

    Default filename is `{sanitized_title}.mp4`. On collision (another video in
    this plan already claims the name, or a pre-existing file on disk belongs to
    a different vimeo_id), the later video gets `{title}_{vimeo_id}.mp4` and a
    warning is logged.
    """
    claimed: dict[Path, str] = {}
    plan: dict[str, Path] = {}

    for account_name, videos in videos_per_account.items():
        for video in videos:
            vid = _video_id(video)
            if not vid:
                logger.warning("raw_download: video has no id, skipping", account=account_name, video=video.get("name"))
                continue

            title = sanitize_title(video.get("name") or vid)
            candidate = output_dir / f"{title}.mp4"

            collision = candidate in claimed and claimed[candidate] != vid
            if not collision and candidate.exists():
                # Pre-existing file belongs to another vimeo_id unless we can prove otherwise
                # via the sidecar. We can't — check the sidecar the downloader writes.
                sidecar = output_dir / "_metadata" / f"{vid}.json"
                if not sidecar.exists():
                    collision = True

            if collision:
                disambiguated = output_dir / f"{title}_{vid}.mp4"
                logger.warning(
                    "raw_download: filename collision, disambiguating with vimeo_id",
                    account=account_name,
                    original=str(candidate.name),
                    resolved=str(disambiguated.name),
                )
                candidate = disambiguated

            claimed[candidate] = vid
            plan[vid] = candidate

    return plan


def pick_download_link(metadata: dict, quality: str) -> str | None:
    """Pick a progressive download URL from Vimeo video metadata.

    For `quality == "best"`, prefers the original `source` rendition, falling
    back to the highest-resolution HD rendition.
    For `"1080p"`/`"720p"`/`"480p"`, matches HD at that rendition.
    """
    downloads = metadata.get("download") or []
    if not downloads:
        return None

    if quality == "best":
        source = next((d for d in downloads if d.get("quality") == "source"), None)
        if source and source.get("link"):
            return source["link"]
        hd = [d for d in downloads if d.get("quality") == "hd"]
        if hd:
            hd.sort(key=lambda d: d.get("height") or 0, reverse=True)
            return hd[0].get("link")
        return None

    match = next(
        (d for d in downloads if d.get("quality") == "hd" and d.get("rendition") == quality),
        None,
    )
    return match.get("link") if match else None


def get_video_metadata(client: VimeoClient, vimeo_id: str) -> dict:
    """Fetch full per-video metadata (includes `download` array)."""
    response = client.get(f"https://api.vimeo.com/videos/{vimeo_id}")
    if response.status_code != _HTTP_OK:
        logger.error("Vimeo metadata fetch failed", vimeo_id=vimeo_id, status=response.status_code)
        return {}
    return response.json()


class _NoDownloadLinkError(Exception):
    """Raised when the Vimeo entry has no download array — not a transient error, don't retry."""


def _attempt_download_one(
    client: VimeoClient,
    video: dict,
    target_path: Path,
    quality: str,
) -> Path:
    """Single download attempt. Raises on transient failures (retryable).

    Raises `_NoDownloadLinkError` if the video has no download link (non-retryable).
    Returns the final target_path on success.
    """
    vid = _video_id(video)
    metadata = get_video_metadata(client, vid)
    if not metadata:
        raise requests.RequestException(f"metadata fetch failed for {vid}")

    link = pick_download_link(metadata, quality)
    if not link:
        raise _NoDownloadLinkError(
            f"no download link available for {vid} (probably a live-event shell)"
        )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = target_path.with_suffix(target_path.suffix + ".part")

    metadata_dir = target_path.parent / "_metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    (metadata_dir / f"{vid}.json").write_text(json.dumps(metadata, indent=2))

    try:
        with requests.get(link, stream=True, timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT)) as response:
            if response.status_code != _HTTP_OK:
                raise requests.RequestException(f"HTTP {response.status_code} for {vid}")
            with part_path.open("wb") as f:
                for chunk in response.iter_content(chunk_size=_CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
    except (requests.RequestException, OSError):
        if part_path.exists():
            part_path.unlink()
        raise

    part_path.rename(target_path)
    return target_path


def download_one(
    client: VimeoClient,
    video: dict,
    target_path: Path,
    quality: str,
    retry_max_attempts: int = _DEFAULT_RETRY_MAX_ATTEMPTS,
) -> Path | None:
    """Stream one video to disk with retry on transient errors.

    Writes to `{target_path}.part` first, atomic-renames on success. Also writes
    `{output_dir}/_metadata/{vimeo_id}.json` for audit. Retries up to
    `retry_max_attempts` times on network/HTTP errors with exponential backoff.
    Does NOT retry when the video has no download link (non-transient).
    """
    vid = _video_id(video)
    total_attempts = retry_max_attempts + 1

    for attempt_index in range(total_attempts):
        try:
            path = _attempt_download_one(client, video, target_path, quality)
            if attempt_index > 0:
                logger.info(
                    "raw_download: downloaded after retry",
                    vimeo_id=vid,
                    attempt=attempt_index + 1,
                    path=str(path),
                )
            else:
                logger.info("raw_download: downloaded", vimeo_id=vid, path=str(path))
            return path
        except _NoDownloadLinkError:
            logger.warning(
                "raw_download: no download link available (probably a live-event shell)",
                vimeo_id=vid,
                title=video.get("name"),
            )
            break
        except (requests.RequestException, OSError) as exc:
            if attempt_index + 1 < total_attempts:
                wait = _backoff_seconds(attempt_index)
                logger.warning(
                    "raw_download: attempt failed, retrying",
                    vimeo_id=vid,
                    attempt=attempt_index + 1,
                    max_attempts=total_attempts,
                    wait_seconds=wait,
                    error=str(exc),
                )
                time.sleep(wait)
            else:
                logger.error(
                    "raw_download: giving up after retries",
                    vimeo_id=vid,
                    attempts=total_attempts,
                    error=str(exc),
                )
    return None


def download_account(
    account: dict[str, Any],
    plan_for_account: list[tuple[dict, Path]],
    download_cfg: dict[str, Any],
    semaphore: threading.Semaphore,
    progress_cb: Callable[[str, int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Run downloads for one account, respecting the global semaphore.

    `plan_for_account` is a list of (video_dict, target_path) pairs — already
    filtered for skip_existing at the caller level if appropriate.
    """
    client = make_client(account)
    quality = download_cfg.get("quality", "best")
    skip_existing = download_cfg.get("skip_existing", True)
    retry_max_attempts = int(download_cfg.get("retry_max_attempts", _DEFAULT_RETRY_MAX_ATTEMPTS))
    name = account["name"]

    results = {"downloaded": [], "skipped": [], "failed": []}
    total = len(plan_for_account)
    lock = threading.Lock()
    completed = 0

    # Register the progress bar eagerly so every account shows up in the UI immediately,
    # even before its first video finishes. Otherwise bars appear lazily (first skip/complete).
    if total > 0:
        _progress(progress_cb, name, 0, total, "starting")

    def worker(video: dict, target: Path) -> None:
        nonlocal completed
        vid = _video_id(video)
        if skip_existing and target.exists():
            with lock:
                results["skipped"].append(target)
                completed += 1
                _progress(progress_cb, name, completed, total, f"skipped {target.name}")
            logger.info("raw_download: skip (already downloaded)", vimeo_id=vid, path=str(target))
            return
        with semaphore:
            path = download_one(client, video, target, quality, retry_max_attempts=retry_max_attempts)
        with lock:
            if path is not None:
                results["downloaded"].append(path)
            else:
                results["failed"].append(vid)
            completed += 1
            _progress(progress_cb, name, completed, total, f"done {target.name}")

    threads = [threading.Thread(target=worker, args=(v, t)) for v, t in plan_for_account]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    return results


def _progress(
    progress_cb: Callable[[str, int, int, str], None] | None,
    account: str,
    current: int,
    total: int,
    message: str,
) -> None:
    if progress_cb:
        progress_cb(account, current, total, message)


def _select_and_filter(
    account: dict[str, Any],
    blocked_ids: set[str],
    blocked_titles: set[str],
    limit: int | None,
) -> list[dict]:
    """List this account's videos from Vimeo, filter out blocked ones, honor `limit`."""
    client = make_client(account)
    selection = dict(account.get("selection") or {})
    raw_videos = select_videos_for_account(client, selection, account.get("user_id"))

    videos: list[dict] = []
    blocked = 0
    for v in raw_videos:
        vid = _video_id(v)
        title = sanitize_title(v.get("name") or vid)
        if vid in blocked_ids or title in blocked_titles:
            blocked += 1
            logger.info(
                "raw_download: skipped (in removed dir)",
                account=account["name"],
                vimeo_id=vid,
                title=title,
            )
            continue
        videos.append(v)

    if limit:
        videos = videos[:limit]
    logger.info(
        "raw_download: selected videos",
        account=account["name"],
        count=len(videos),
        blocked=blocked,
    )
    return videos


def run(
    config: Any,
    accounts_filter: tuple[str, ...] | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    progress_cb: Callable[[str, int, int, str], None] | None = None,
) -> dict[str, dict[str, Any]]:
    """Top-level entry point.

    Returns a mapping `{account_name: {downloaded, skipped, failed, plan}}`.
    In `dry_run` mode, returns after computing the rename plan; no HTTP downloads,
    no sidecar writes.
    """
    raw_sources = config.vimeo.raw_sources
    accounts = [dict(a) for a in (raw_sources.get("accounts") or [])]
    if not accounts:
        raise ValueError("vimeo.raw_sources.accounts: no source accounts configured")

    if accounts_filter:
        wanted = set(accounts_filter)
        accounts = [a for a in accounts if a["name"] in wanted]
        missing = wanted - {a["name"] for a in accounts}
        if missing:
            raise ValueError(f"unknown account(s): {', '.join(sorted(missing))}")

    download_cfg = dict(raw_sources.download)
    output_dir = Path(download_cfg["output_dir"])
    max_concurrent = int(download_cfg.get("max_concurrent", 2))

    removed_dir = output_dir / _REMOVED_DIRNAME
    blocked_ids, blocked_titles = load_blocklist(removed_dir)
    if blocked_ids or blocked_titles:
        logger.info(
            "raw_download: blocklist loaded",
            removed_dir=str(removed_dir),
            blocked_ids=len(blocked_ids),
            blocked_titles=len(blocked_titles),
        )

    videos_per_account: dict[str, list[dict]] = {
        account["name"]: _select_and_filter(account, blocked_ids, blocked_titles, limit)
        for account in accounts
    }

    plan = plan_filenames(videos_per_account, output_dir)

    summary: dict[str, dict[str, Any]] = {}
    if dry_run:
        for account in accounts:
            name = account["name"]
            entries = [
                {"vimeo_id": _video_id(v), "title": v.get("name"), "target": plan[_video_id(v)]}
                for v in videos_per_account[name]
                if _video_id(v) in plan
            ]
            summary[name] = {"downloaded": [], "skipped": [], "failed": [], "plan": entries}
        return summary

    max_accounts_concurrent = int(download_cfg.get("max_accounts_concurrent", 1))
    accounts_semaphore = threading.Semaphore(max_accounts_concurrent)
    summary_lock = threading.Lock()

    def account_thread(account: dict[str, Any]) -> None:
        name = account["name"]
        account_plan = [(v, plan[_video_id(v)]) for v in videos_per_account[name] if _video_id(v) in plan]
        with accounts_semaphore:
            per_account_sem = threading.Semaphore(max_concurrent)
            results = download_account(account, account_plan, download_cfg, per_account_sem, progress_cb)
        with summary_lock:
            summary[name] = {
                **results,
                "plan": [{"vimeo_id": _video_id(v), "target": p} for v, p in account_plan],
            }

    threads = [
        threading.Thread(target=account_thread, args=(a,), name=f"acct:{a['name']}") for a in accounts
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    return summary
