"""Regression tests for the pytanis `submission_type` round-trip.

pytanis' `Submission.mangle_submission_type` validator is not idempotent: it
replaces the submission_type object by its `name`, so validating an already-stored
record a second time nulls the field. Any code that then writes the record back
persists that null and the record becomes permanently unloadable — silently, since
`add_descriptions` catches per-record errors and just reports "0 added".

This happened twice: once via the fetch path and once via the description
write-back. These tests pin both directions.
"""

import json

from manager.handlers.records import load_session_record, unmangle_submission_type

SUBMISSION_TYPE = {"en": "Talk", "de": None}
SUBMISSION_TYPE_ID = 6779


def _record_payload(session_extra: dict) -> dict:
    """A minimal SessionRecord payload; only the fields the loader touches matter."""
    session = {
        "code": "ABC123",
        "title": "A talk",
        "abstract": "Abstract.",
        "description": "Description.",
        "speakers": [],
        "do_not_record": False,
        "state": "confirmed",
        "resources": [],
        "slots": [],
        "answers": [],
        "created": "2026-01-01T00:00:00Z",
        "duration": 30,
        "slot_count": 1,
        **session_extra,
    }
    return {
        "pretalx_session": {"pretalx_id": "ABC123", "title": "A talk", "session": session, "speakers": []},
        "pretalx_id": "ABC123",
        "title": "A talk",
        "abstract": "Abstract.",
        "description": "Description.",
        "speakers": [],
        "sm_teaser_text": "",
        "sm_short_text": "",
        "sm_long_text": "",
    }


class TestUnmangleSubmissionType:
    def test_renests_already_mangled_value(self):
        out = unmangle_submission_type(
            {"submission_type": SUBMISSION_TYPE, "submission_type_id": SUBMISSION_TYPE_ID}
        )
        assert out["submission_type"] == {"id": SUBMISSION_TYPE_ID, "name": SUBMISSION_TYPE}

    def test_is_a_no_op_on_fresh_api_data(self):
        fresh = {"submission_type": {"id": SUBMISSION_TYPE_ID, "name": SUBMISSION_TYPE}}
        assert unmangle_submission_type(fresh) == fresh

    def test_is_a_no_op_without_an_id_to_restore(self):
        without_id = {"submission_type": SUBMISSION_TYPE}
        assert unmangle_submission_type(without_id) == without_id


class TestLoadSessionRecord:
    def test_keeps_submission_type_on_load(self, tmp_path):
        path = tmp_path / "ABC123.json"
        path.write_text(
            json.dumps(
                _record_payload({"submission_type": SUBMISSION_TYPE, "submission_type_id": SUBMISSION_TYPE_ID})
            )
        )
        record = load_session_record(path)
        assert record.pretalx_session.session.submission_type is not None

    def test_write_back_does_not_null_the_field(self, tmp_path):
        """The actual regression: load -> dump -> load must survive."""
        path = tmp_path / "ABC123.json"
        path.write_text(
            json.dumps(
                _record_payload({"submission_type": SUBMISSION_TYPE, "submission_type_id": SUBMISSION_TYPE_ID})
            )
        )

        record = load_session_record(path)
        path.write_text(record.model_dump_json(indent=4))

        stored = json.loads(path.read_text())["pretalx_session"]["session"]["submission_type"]
        assert stored is not None, "write-back nulled submission_type — the record is now unloadable"
        load_session_record(path)  # must not raise
