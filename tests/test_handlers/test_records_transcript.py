"""Tests for the optional transcript-based description feature.

Covers:
- load_transcript() folder/prefix matching
- Records._apply_descriptions() branch selection (transcript vs abstract)
- ai_service.summary_from_transcript() transcript truncation
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from manager.handlers import ai_service
from manager.handlers import records as records_mod
from manager.handlers.records import Records, load_transcript

CONFIG_MAX_CHARS = 48000  # config.yaml default for transcripts.max_chars
EXPECTED_DESC_CALLS = 2  # short + long


def _fake_record(code: str = "37AESH") -> SimpleNamespace:
    """Minimal stand-in exposing the attributes _apply_descriptions touches."""
    speaker = SimpleNamespace(name="Jane Doe", job="Engineer", biography="Bio.")
    return SimpleNamespace(
        pretalx_id=code,
        title="A Great Talk",
        abstract="Abstract.",
        description="Description.",
        speakers=[speaker],
        sm_teaser_text="",
        sm_short_text="",
        sm_long_text="",
    )


class TestLoadTranscript:
    def test_returns_none_without_root(self):
        assert load_transcript("37AESH", None) is None

    def test_matches_folder_by_code_prefix(self, tmp_path):
        talk_dir = tmp_path / "37AESH_a-great-talk"
        talk_dir.mkdir()
        (talk_dir / "transcript.md").write_text("hello transcript")
        assert load_transcript("37AESH", tmp_path) == "hello transcript"

    def test_returns_none_when_folder_missing_transcript_file(self, tmp_path):
        (tmp_path / "37AESH_talk").mkdir()
        assert load_transcript("37AESH", tmp_path) is None

    def test_returns_none_when_no_matching_folder(self, tmp_path):
        other = tmp_path / "ZZZZZZ_talk"
        other.mkdir()
        (other / "transcript.md").write_text("nope")
        assert load_transcript("37AESH", tmp_path) is None


class TestApplyDescriptionsBranch:
    def test_uses_transcript_summary_when_present(self, tmp_path):
        talk_dir = tmp_path / "37AESH_talk"
        talk_dir.mkdir()
        (talk_dir / "transcript.md").write_text("the real transcript text")
        data = _fake_record("37AESH")

        with (
            patch.object(records_mod, "teaser_text", return_value="teaser") as m_teaser,
            patch.object(records_mod, "sized_text", return_value="sized") as m_sized,
            patch.object(records_mod, "summary_from_transcript", return_value="summary") as m_summary,
        ):
            added = Records._apply_descriptions(data, replace=False, transcripts_root=tmp_path)

        assert added is True
        assert data.sm_short_text == "summary"
        assert data.sm_long_text == "summary"
        assert data.sm_teaser_text == "teaser"
        m_teaser.assert_called_once()
        m_summary.assert_called()  # short + long
        m_sized.assert_not_called()

    def test_uses_abstract_when_no_transcript(self, tmp_path):
        data = _fake_record("37AESH")

        with (
            patch.object(records_mod, "teaser_text", return_value="teaser"),
            patch.object(records_mod, "sized_text", return_value="sized") as m_sized,
            patch.object(records_mod, "summary_from_transcript", return_value="summary") as m_summary,
        ):
            added = Records._apply_descriptions(data, replace=False, transcripts_root=tmp_path)

        assert added is True
        assert data.sm_short_text == "sized"
        assert data.sm_long_text == "sized"
        m_summary.assert_not_called()
        assert m_sized.call_count == EXPECTED_DESC_CALLS

    def test_skips_regeneration_when_already_filled(self, tmp_path):
        data = _fake_record("37AESH")
        data.sm_teaser_text = "keep-teaser"
        data.sm_short_text = "keep-short"
        data.sm_long_text = "keep-long"

        with (
            patch.object(records_mod, "teaser_text") as m_teaser,
            patch.object(records_mod, "sized_text") as m_sized,
            patch.object(records_mod, "summary_from_transcript") as m_summary,
        ):
            added = Records._apply_descriptions(data, replace=False, transcripts_root=tmp_path)

        assert added is False
        m_teaser.assert_not_called()
        m_sized.assert_not_called()
        m_summary.assert_not_called()
        assert data.sm_short_text == "keep-short"


class TestSummaryTruncation:
    def test_transcript_is_clipped_to_max_chars(self):
        captured = {}

        def fake_generate(**kwargs):
            captured.update(kwargs)
            return "ok"

        provider = MagicMock()
        provider.generate_text.side_effect = fake_generate

        long_transcript = "x" * 100_000
        with patch.object(ai_service, "get_ai_provider", return_value=provider):
            ai_service.summary_from_transcript(long_transcript, grounding="Title: T", max_tokens=300)

        # config default max_chars is 48000; transcript in the prompt must be clipped.
        user_prompt = captured["user_prompt"]
        assert "x" * CONFIG_MAX_CHARS in user_prompt
        assert "x" * (CONFIG_MAX_CHARS + 1) not in user_prompt
