"""Unit tests for `manager.scripts.vimeo_raw_download` and its config validator."""

import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests
from omegaconf import OmegaConf

from manager.config import validate_config
from manager.scripts import vimeo_raw_download as vrd  # noqa: E402

# ------------------------------------------------------------
# sanitize_title
# ------------------------------------------------------------


class TestSanitizeTitle:
    def test_replaces_illegal_chars(self):
        assert vrd.sanitize_title('a/b\\c*d?e"f<g>h|i:j') == "a_b_c_d_e_f_g_h_i_j"

    def test_preserves_spaces_and_ampersand(self):
        # Critical: process_talk_list.py reconstructs "PyConDE & PyData 2025 - Room - Day Period"
        assert (
            vrd.sanitize_title("PyConDE & PyData 2025 - Dynamicum - Friday Morning")
            == "PyConDE & PyData 2025 - Dynamicum - Friday Morning"
        )

    def test_strips_trailing_mp4(self):
        assert vrd.sanitize_title("Recording.mp4") == "Recording"
        assert vrd.sanitize_title("Recording.MP4") == "Recording"

    def test_empty_name_returns_empty(self):
        assert vrd.sanitize_title("") == ""


# ------------------------------------------------------------
# pick_download_link
# ------------------------------------------------------------


class TestPickDownloadLink:
    def test_best_prefers_source(self):
        metadata = {
            "download": [
                {"quality": "source", "link": "src"},
                {"quality": "hd", "rendition": "1080p", "height": 1080, "link": "hd1080"},
            ]
        }
        assert vrd.pick_download_link(metadata, "best") == "src"

    def test_best_falls_back_to_highest_hd(self):
        metadata = {
            "download": [
                {"quality": "hd", "rendition": "720p", "height": 720, "link": "hd720"},
                {"quality": "hd", "rendition": "1080p", "height": 1080, "link": "hd1080"},
            ]
        }
        assert vrd.pick_download_link(metadata, "best") == "hd1080"

    def test_explicit_quality_matches_rendition(self):
        metadata = {
            "download": [
                {"quality": "hd", "rendition": "1080p", "link": "hd1080"},
                {"quality": "hd", "rendition": "720p", "link": "hd720"},
            ]
        }
        assert vrd.pick_download_link(metadata, "720p") == "hd720"

    def test_returns_none_when_no_download_array(self):
        assert vrd.pick_download_link({}, "best") is None
        assert vrd.pick_download_link({"download": []}, "1080p") is None


# ------------------------------------------------------------
# plan_filenames — collision disambiguation
# ------------------------------------------------------------


class TestPlanFilenames:
    def test_unique_titles_keep_clean_names(self, tmp_path):
        videos = {
            "acct": [
                {"uri": "/videos/1001", "name": "Talk A"},
                {"uri": "/videos/1002", "name": "Talk B"},
            ]
        }
        plan = vrd.plan_filenames(videos, tmp_path)
        assert plan["1001"] == tmp_path / "Talk A.mp4"
        assert plan["1002"] == tmp_path / "Talk B.mp4"

    def test_within_account_collision_disambiguates_with_vimeo_id(self, tmp_path):
        videos = {
            "acct": [
                {"uri": "/videos/1001", "name": "Same Title"},
                {"uri": "/videos/1002", "name": "Same Title"},
            ]
        }
        plan = vrd.plan_filenames(videos, tmp_path)
        assert plan["1001"] == tmp_path / "Same Title.mp4"
        assert plan["1002"] == tmp_path / "Same Title_1002.mp4"

    def test_cross_account_collision_disambiguates(self, tmp_path):
        videos = {
            "a": [{"uri": "/videos/1001", "name": "Shared"}],
            "b": [{"uri": "/videos/2002", "name": "Shared"}],
        }
        plan = vrd.plan_filenames(videos, tmp_path)
        assert plan["1001"] == tmp_path / "Shared.mp4"
        assert plan["2002"] == tmp_path / "Shared_2002.mp4"

    def test_preexisting_file_triggers_disambiguation(self, tmp_path):
        # A file is already on disk with no sidecar — treat as collision.
        (tmp_path / "Existing.mp4").write_bytes(b"stub")
        videos = {"acct": [{"uri": "/videos/9999", "name": "Existing"}]}
        plan = vrd.plan_filenames(videos, tmp_path)
        assert plan["9999"] == tmp_path / "Existing_9999.mp4"

    def test_preexisting_file_with_matching_sidecar_is_not_a_collision(self, tmp_path):
        # Sidecar proves the on-disk file is this same vimeo_id; no rename.
        (tmp_path / "Existing.mp4").write_bytes(b"stub")
        metadata_dir = tmp_path / "_metadata"
        metadata_dir.mkdir()
        (metadata_dir / "9999.json").write_text("{}")
        videos = {"acct": [{"uri": "/videos/9999", "name": "Existing"}]}
        plan = vrd.plan_filenames(videos, tmp_path)
        assert plan["9999"] == tmp_path / "Existing.mp4"


# ------------------------------------------------------------
# select_videos_for_account — dispatch
# ------------------------------------------------------------


class TestSelectVideosForAccount:
    def test_folder_id_calls_folder_endpoint(self, monkeypatch):
        client = MagicMock()
        called = {}

        def fake_folder(_c, user_id, folder_id):
            called["args"] = (user_id, folder_id)
            return [{"uri": "/videos/1"}]

        monkeypatch.setattr(vrd, "list_videos_in_folder", fake_folder)
        result = vrd.select_videos_for_account(
            client, {"folder_id": "42"}, user_id="userX"
        )
        assert result == [{"uri": "/videos/1"}]
        assert called["args"] == ("userX", "42")

    def test_folder_id_without_user_id_raises(self):
        with pytest.raises(ValueError, match="user_id required"):
            vrd.select_videos_for_account(MagicMock(), {"folder_id": "42"}, user_id=None)

    def test_title_contains_filters(self, monkeypatch):
        client = MagicMock()

        fake_page = [
            {"uri": "/videos/1", "name": "PyData Berlin 2025 Keynote"},
            {"uri": "/videos/2", "name": "Something else"},
        ]
        monkeypatch.setattr(vrd, "_paginate", lambda *_args, **_kw: list(fake_page))
        result = vrd.select_videos_for_account(
            client, {"title_contains": "pydata berlin"}, user_id=None
        )
        assert [v["uri"] for v in result] == ["/videos/1"]

    def test_title_regex_filters(self, monkeypatch):
        monkeypatch.setattr(
            vrd,
            "_paginate",
            lambda *_args, **_kw: [
                {"uri": "/videos/1", "name": "Day 1 Morning"},
                {"uri": "/videos/2", "name": "Day 2 Morning"},
                {"uri": "/videos/3", "name": "Day 1 Afternoon"},
            ],
        )
        result = vrd.select_videos_for_account(
            MagicMock(), {"title_regex": r"^Day \d Morning$"}, user_id=None
        )
        assert [v["uri"] for v in result] == ["/videos/1", "/videos/2"]

    def test_empty_selection_raises(self):
        with pytest.raises(ValueError, match="exactly one"):
            vrd.select_videos_for_account(MagicMock(), {}, user_id=None)


# ------------------------------------------------------------
# Config validator
# ------------------------------------------------------------


def _base_config(output_dir: Path) -> dict:
    """Minimum config shape to exercise validate_config cleanly."""
    return {
        "dirs": {"work_dir": output_dir / "_tmp", "video_dir": output_dir / "videos"},
        "pretalx": {"event_slug": "test-event"},
        "youtube": {
            "channels": {"main": {"id": "UC_main", "playlist_id": "PL_main"}},
            "api_key": "dummy",
        },
        "vimeo": {"raw_sources": {"accounts": [], "download": {"output_dir": str(output_dir), "quality": "best", "max_concurrent": 2}}},
    }


def _valid_account(name: str = "main") -> dict:
    return {
        "name": name,
        "access_token": "tok",
        "client_id": "cid",
        "client_secret": "cse",
        "user_id": "42",
        "selection": {"folder_id": "100"},
    }


class TestValidateRawSources:
    def test_empty_accounts_is_not_validated(self, tmp_path):
        """Users who haven't configured raw_sources yet should not be blocked."""
        cfg = OmegaConf.create(_base_config(tmp_path))
        cfg.dirs.work_dir.mkdir(parents=True, exist_ok=True)
        errors, _ = validate_config(cfg)
        assert not any("raw_sources" in e for e in errors)

    def test_valid_config_passes(self, tmp_path):
        data = _base_config(tmp_path)
        data["vimeo"]["raw_sources"]["accounts"] = [_valid_account()]
        cfg = OmegaConf.create(data)
        cfg.dirs.work_dir.mkdir(parents=True, exist_ok=True)
        errors, _ = validate_config(cfg)
        assert not any("raw_sources" in e for e in errors), errors

    def test_accepts_many_accounts(self, tmp_path):
        """Design is 1-N: any number of accounts is valid."""
        data = _base_config(tmp_path)
        data["vimeo"]["raw_sources"]["accounts"] = [
            _valid_account(f"a{i}") for i in range(10)
        ]
        cfg = OmegaConf.create(data)
        cfg.dirs.work_dir.mkdir(parents=True, exist_ok=True)
        errors, _ = validate_config(cfg)
        assert not any("raw_sources" in e for e in errors), errors

    def test_rejects_duplicate_names(self, tmp_path):
        data = _base_config(tmp_path)
        data["vimeo"]["raw_sources"]["accounts"] = [_valid_account("same"), _valid_account("same")]
        cfg = OmegaConf.create(data)
        cfg.dirs.work_dir.mkdir(parents=True, exist_ok=True)
        errors, _ = validate_config(cfg)
        assert any("duplicate account name 'same'" in e for e in errors)

    def test_rejects_missing_credentials(self, tmp_path):
        data = _base_config(tmp_path)
        bad = _valid_account()
        del bad["access_token"]
        data["vimeo"]["raw_sources"]["accounts"] = [bad]
        cfg = OmegaConf.create(data)
        cfg.dirs.work_dir.mkdir(parents=True, exist_ok=True)
        errors, _ = validate_config(cfg)
        assert any("missing access_token" in e for e in errors)

    def test_rejects_zero_selection_keys(self, tmp_path):
        data = _base_config(tmp_path)
        bad = _valid_account()
        bad["selection"] = {}
        data["vimeo"]["raw_sources"]["accounts"] = [bad]
        cfg = OmegaConf.create(data)
        cfg.dirs.work_dir.mkdir(parents=True, exist_ok=True)
        errors, _ = validate_config(cfg)
        assert any("selection must set exactly one" in e for e in errors)

    def test_rejects_multiple_selection_keys(self, tmp_path):
        data = _base_config(tmp_path)
        bad = _valid_account()
        bad["selection"] = {"folder_id": "1", "title_contains": "x"}
        data["vimeo"]["raw_sources"]["accounts"] = [bad]
        cfg = OmegaConf.create(data)
        cfg.dirs.work_dir.mkdir(parents=True, exist_ok=True)
        errors, _ = validate_config(cfg)
        assert any("selection must set exactly one" in e for e in errors)

    def test_rejects_folder_id_without_user_id(self, tmp_path):
        data = _base_config(tmp_path)
        bad = _valid_account()
        bad["user_id"] = ""
        data["vimeo"]["raw_sources"]["accounts"] = [bad]
        cfg = OmegaConf.create(data)
        cfg.dirs.work_dir.mkdir(parents=True, exist_ok=True)
        errors, _ = validate_config(cfg)
        assert any("user_id required" in e for e in errors)

    def test_rejects_nonexistent_output_dir(self, tmp_path):
        data = _base_config(tmp_path)
        data["vimeo"]["raw_sources"]["accounts"] = [_valid_account()]
        data["vimeo"]["raw_sources"]["download"]["output_dir"] = str(tmp_path / "does_not_exist")
        cfg = OmegaConf.create(data)
        cfg.dirs.work_dir.mkdir(parents=True, exist_ok=True)
        errors, _ = validate_config(cfg)
        assert any("does not exist" in e for e in errors)

    def test_rejects_bad_quality(self, tmp_path):
        data = _base_config(tmp_path)
        data["vimeo"]["raw_sources"]["accounts"] = [_valid_account()]
        data["vimeo"]["raw_sources"]["download"]["quality"] = "ultra"
        cfg = OmegaConf.create(data)
        cfg.dirs.work_dir.mkdir(parents=True, exist_ok=True)
        errors, _ = validate_config(cfg)
        assert any("quality: must be one of" in e for e in errors)

    def test_rejects_zero_or_negative_max_concurrent(self, tmp_path):
        data = _base_config(tmp_path)
        data["vimeo"]["raw_sources"]["accounts"] = [_valid_account()]
        data["vimeo"]["raw_sources"]["download"]["max_concurrent"] = 0
        cfg = OmegaConf.create(data)
        cfg.dirs.work_dir.mkdir(parents=True, exist_ok=True)
        errors, _ = validate_config(cfg)
        assert any("max_concurrent" in e for e in errors)

    def test_accepts_high_max_concurrent(self, tmp_path):
        """No upper cap on concurrency — user's choice."""
        data = _base_config(tmp_path)
        data["vimeo"]["raw_sources"]["accounts"] = [_valid_account()]
        data["vimeo"]["raw_sources"]["download"]["max_concurrent"] = 99
        cfg = OmegaConf.create(data)
        cfg.dirs.work_dir.mkdir(parents=True, exist_ok=True)
        errors, _ = validate_config(cfg)
        assert not any("max_concurrent" in e for e in errors), errors

    def test_max_accounts_concurrent_absent_is_ok(self, tmp_path):
        """Absent max_accounts_concurrent is fine — defaults to 1 at runtime."""
        data = _base_config(tmp_path)
        data["vimeo"]["raw_sources"]["accounts"] = [_valid_account()]
        # Don't set max_accounts_concurrent at all.
        cfg = OmegaConf.create(data)
        cfg.dirs.work_dir.mkdir(parents=True, exist_ok=True)
        errors, _ = validate_config(cfg)
        assert not any("max_accounts_concurrent" in e for e in errors), errors

    def test_rejects_zero_max_accounts_concurrent(self, tmp_path):
        data = _base_config(tmp_path)
        data["vimeo"]["raw_sources"]["accounts"] = [_valid_account()]
        data["vimeo"]["raw_sources"]["download"]["max_accounts_concurrent"] = 0
        cfg = OmegaConf.create(data)
        cfg.dirs.work_dir.mkdir(parents=True, exist_ok=True)
        errors, _ = validate_config(cfg)
        assert any("max_accounts_concurrent" in e for e in errors)

    def test_accepts_high_max_accounts_concurrent(self, tmp_path):
        data = _base_config(tmp_path)
        data["vimeo"]["raw_sources"]["accounts"] = [_valid_account()]
        data["vimeo"]["raw_sources"]["download"]["max_accounts_concurrent"] = 50
        cfg = OmegaConf.create(data)
        cfg.dirs.work_dir.mkdir(parents=True, exist_ok=True)
        errors, _ = validate_config(cfg)
        assert not any("max_accounts_concurrent" in e for e in errors), errors

    def test_retry_max_attempts_absent_is_ok(self, tmp_path):
        """Absent retry_max_attempts is fine — defaults to 3 at runtime."""
        data = _base_config(tmp_path)
        data["vimeo"]["raw_sources"]["accounts"] = [_valid_account()]
        cfg = OmegaConf.create(data)
        cfg.dirs.work_dir.mkdir(parents=True, exist_ok=True)
        errors, _ = validate_config(cfg)
        assert not any("retry_max_attempts" in e for e in errors), errors

    def test_retry_max_attempts_zero_is_ok(self, tmp_path):
        """0 means never retry — valid."""
        data = _base_config(tmp_path)
        data["vimeo"]["raw_sources"]["accounts"] = [_valid_account()]
        data["vimeo"]["raw_sources"]["download"]["retry_max_attempts"] = 0
        cfg = OmegaConf.create(data)
        cfg.dirs.work_dir.mkdir(parents=True, exist_ok=True)
        errors, _ = validate_config(cfg)
        assert not any("retry_max_attempts" in e for e in errors), errors

    def test_rejects_negative_retry_max_attempts(self, tmp_path):
        data = _base_config(tmp_path)
        data["vimeo"]["raw_sources"]["accounts"] = [_valid_account()]
        data["vimeo"]["raw_sources"]["download"]["retry_max_attempts"] = -1
        cfg = OmegaConf.create(data)
        cfg.dirs.work_dir.mkdir(parents=True, exist_ok=True)
        errors, _ = validate_config(cfg)
        assert any("retry_max_attempts" in e for e in errors)


# ------------------------------------------------------------
# download_one retry behavior
# ------------------------------------------------------------


class TestDownloadOneRetry:
    RETRIES = 3
    SUCCESS_ON_ATTEMPT = 3  # fails on attempts 1 and 2, succeeds on attempt 3
    TOTAL_ATTEMPTS_WHEN_EXHAUSTED = RETRIES + 1  # initial + retries

    @pytest.fixture(autouse=True)
    def fast_backoff(self, monkeypatch):
        """Neutralize the exponential backoff so tests don't sleep seconds."""
        monkeypatch.setattr(vrd.time, "sleep", lambda _s: None)

    def test_retries_then_succeeds(self, tmp_path, monkeypatch):
        calls = {"n": 0}

        def fake_attempt(_client, _video, target, _quality):
            calls["n"] += 1
            if calls["n"] < self.SUCCESS_ON_ATTEMPT:
                raise requests.RequestException(f"transient error {calls['n']}")
            target.write_bytes(b"video")
            return target

        monkeypatch.setattr(vrd, "_attempt_download_one", fake_attempt)

        result = vrd.download_one(
            MagicMock(), {"uri": "/videos/42"}, tmp_path / "x.mp4", "best", retry_max_attempts=self.RETRIES
        )
        assert result == tmp_path / "x.mp4"
        assert calls["n"] == self.SUCCESS_ON_ATTEMPT

    def test_gives_up_after_retries_exhausted(self, tmp_path, monkeypatch):
        calls = {"n": 0}

        def fake_attempt(*_a, **_kw):
            calls["n"] += 1
            raise requests.RequestException("always broken")

        monkeypatch.setattr(vrd, "_attempt_download_one", fake_attempt)

        result = vrd.download_one(
            MagicMock(), {"uri": "/videos/42"}, tmp_path / "x.mp4", "best", retry_max_attempts=self.RETRIES
        )
        assert result is None
        assert calls["n"] == self.TOTAL_ATTEMPTS_WHEN_EXHAUSTED

    def test_retry_zero_tries_once(self, tmp_path, monkeypatch):
        """retry_max_attempts=0 means no retry — exactly one attempt."""
        calls = {"n": 0}

        def fake_attempt(*_a, **_kw):
            calls["n"] += 1
            raise requests.RequestException("broken")

        monkeypatch.setattr(vrd, "_attempt_download_one", fake_attempt)

        vrd.download_one(
            MagicMock(), {"uri": "/videos/42"}, tmp_path / "x.mp4", "best", retry_max_attempts=0
        )
        assert calls["n"] == 1

    def test_no_download_link_does_not_retry(self, tmp_path, monkeypatch):
        """Shell/live-event entries with no download array are non-transient — no retry."""
        calls = {"n": 0}

        def fake_attempt(*_a, **_kw):
            calls["n"] += 1
            raise vrd._NoDownloadLinkError("nope")

        monkeypatch.setattr(vrd, "_attempt_download_one", fake_attempt)

        result = vrd.download_one(
            MagicMock(),
            {"uri": "/videos/42", "name": "live"},
            tmp_path / "x.mp4",
            "best",
            retry_max_attempts=self.RETRIES,
        )
        assert result is None
        assert calls["n"] == 1  # no retry despite retry_max_attempts > 0


# ------------------------------------------------------------
# Blocklist — files moved to {output_dir}/removed/ must be skipped
# ------------------------------------------------------------


class TestLoadBlocklist:
    def test_missing_removed_dir_is_empty_blocklist(self, tmp_path):
        ids, titles = vrd.load_blocklist(tmp_path / "does_not_exist")
        assert ids == set()
        assert titles == set()

    def test_bare_title_blocks_by_title_only(self, tmp_path):
        (tmp_path / "Break Slide.mp4").write_bytes(b"")
        ids, titles = vrd.load_blocklist(tmp_path)
        assert ids == set()
        assert titles == {"Break Slide"}

    def test_disambiguated_filename_blocks_by_id_and_title(self, tmp_path):
        # {title}_{vimeo_id}.mp4 → block both the id and the stripped title.
        (tmp_path / "Platinum Thursday PM_1182452077.mp4").write_bytes(b"")
        ids, titles = vrd.load_blocklist(tmp_path)
        assert ids == {"1182452077"}
        assert titles == {"Platinum Thursday PM"}

    def test_ignores_non_mp4(self, tmp_path):
        (tmp_path / "notes.txt").write_text("x")
        (tmp_path / "Blocked.mp4").write_bytes(b"")
        ids, titles = vrd.load_blocklist(tmp_path)
        assert titles == {"Blocked"}

    def test_short_trailing_digits_are_not_vimeo_ids(self, tmp_path):
        # "Part_2.mp4" isn't a vimeo_id suffix — 1 digit, below the 6-digit threshold.
        (tmp_path / "Part_2.mp4").write_bytes(b"")
        ids, titles = vrd.load_blocklist(tmp_path)
        assert ids == set()
        assert titles == {"Part_2"}


class TestBlocklistFilteringInRun:
    EXPECTED_UNFILTERED_COUNT = 2

    def _valid_config(self, output_dir):
        return OmegaConf.create(
            {
                "vimeo": {
                    "raw_sources": {
                        "accounts": [_valid_account("main")],
                        "download": {
                            "output_dir": str(output_dir),
                            "quality": "best",
                            "max_concurrent": 1,
                            "max_accounts_concurrent": 1,
                            "skip_existing": True,
                        },
                    }
                }
            }
        )

    def test_videos_in_removed_are_filtered_out(self, tmp_path, monkeypatch):
        output_dir = tmp_path / "downloads"
        output_dir.mkdir()
        removed = output_dir / "removed"
        removed.mkdir()
        # Block by bare title.
        (removed / "Break Slides Only.mp4").write_bytes(b"")
        # Block by vimeo_id.
        (removed / "Some Other Title_1234567890.mp4").write_bytes(b"")

        # Three videos from Vimeo: one blocked by title, one blocked by id, one clean.
        vimeo_videos = [
            {"uri": "/videos/999", "name": "Break Slides Only"},
            {"uri": "/videos/1234567890", "name": "Different Name"},
            {"uri": "/videos/555", "name": "Real Talk"},
        ]
        monkeypatch.setattr(vrd, "make_client", lambda _a: object())
        monkeypatch.setattr(vrd, "select_videos_for_account", lambda *_a, **_kw: vimeo_videos)
        monkeypatch.setattr(vrd, "download_account", lambda *_a, **_kw: {"downloaded": [], "skipped": [], "failed": []})

        cfg = self._valid_config(output_dir)
        summary = vrd.run(cfg)

        # Only the "Real Talk" video should survive into the plan.
        assert "main" in summary
        plan_entries = summary["main"]["plan"]
        assert len(plan_entries) == 1
        assert plan_entries[0]["vimeo_id"] == "555"

    def test_no_removed_dir_means_no_filtering(self, tmp_path, monkeypatch):
        output_dir = tmp_path / "downloads"
        output_dir.mkdir()
        # No `removed/` subdir at all.

        vimeo_videos = [
            {"uri": "/videos/111", "name": "Talk A"},
            {"uri": "/videos/222", "name": "Talk B"},
        ]
        monkeypatch.setattr(vrd, "make_client", lambda _a: object())
        monkeypatch.setattr(vrd, "select_videos_for_account", lambda *_a, **_kw: vimeo_videos)
        monkeypatch.setattr(vrd, "download_account", lambda *_a, **_kw: {"downloaded": [], "skipped": [], "failed": []})

        cfg = self._valid_config(output_dir)
        summary = vrd.run(cfg)
        assert len(summary["main"]["plan"]) == self.EXPECTED_UNFILTERED_COUNT


# ------------------------------------------------------------
# Runtime parallelism proof — accounts must run concurrently
# when max_accounts_concurrent > 1.
# ------------------------------------------------------------


class TestAccountParallelism:
    def _make_run_config(self, tmp_path, accounts, max_accounts_concurrent):
        """Build a DictConfig that run() accepts."""
        return OmegaConf.create(
            {
                "vimeo": {
                    "raw_sources": {
                        "accounts": accounts,
                        "download": {
                            "output_dir": str(tmp_path),
                            "quality": "best",
                            "max_concurrent": 1,
                            "max_accounts_concurrent": max_accounts_concurrent,
                            "skip_existing": True,
                        },
                    }
                }
            }
        )

    def test_accounts_run_in_parallel_when_opted_in(self, tmp_path, monkeypatch):
        accounts = [_valid_account(f"acct{i}") for i in range(3)]
        # Stub out everything that would hit the network.
        monkeypatch.setattr(vrd, "make_client", lambda _account: object())
        monkeypatch.setattr(vrd, "select_videos_for_account", lambda *_a, **_kw: [])
        monkeypatch.setattr(vrd, "plan_filenames", lambda *_a, **_kw: {})

        barrier = threading.Barrier(parties=3, timeout=3.0)

        def fake_download_account(*_a, **_kw):
            # If accounts ran serially, barrier.wait() would time out before 3 parties arrive.
            barrier.wait()
            return {"downloaded": [], "skipped": [], "failed": []}

        monkeypatch.setattr(vrd, "download_account", fake_download_account)

        cfg = self._make_run_config(tmp_path, accounts, max_accounts_concurrent=3)
        # Does not raise BrokenBarrierError → all three threads entered together.
        summary = vrd.run(cfg)
        assert set(summary.keys()) == {"acct0", "acct1", "acct2"}

    def test_accounts_run_serially_by_default(self, tmp_path, monkeypatch):
        """max_accounts_concurrent=1 → only one account in download_account at a time."""
        accounts = [_valid_account(f"acct{i}") for i in range(3)]
        monkeypatch.setattr(vrd, "make_client", lambda _account: object())
        monkeypatch.setattr(vrd, "select_videos_for_account", lambda *_a, **_kw: [])
        monkeypatch.setattr(vrd, "plan_filenames", lambda *_a, **_kw: {})

        in_flight = 0
        peak = 0
        peak_lock = threading.Lock()

        def fake_download_account(*_a, **_kw):
            nonlocal in_flight, peak
            with peak_lock:
                in_flight += 1
                peak = max(peak, in_flight)
            # Hold the slot briefly so a second thread has time to enter if it were allowed.
            threading.Event().wait(0.02)
            with peak_lock:
                in_flight -= 1
            return {"downloaded": [], "skipped": [], "failed": []}

        monkeypatch.setattr(vrd, "download_account", fake_download_account)

        cfg = self._make_run_config(tmp_path, accounts, max_accounts_concurrent=1)
        vrd.run(cfg)
        assert peak == 1, f"expected serial (peak=1), observed peak={peak}"
