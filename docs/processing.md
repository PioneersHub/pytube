# Processing Pipeline

For each video a record is created.

## Known upstream issue — do not remove the `submission_type` workaround

`src/manager/handlers/records.py` contains a workaround for a bug in **pytanis**
that is easy to mistake for redundant defensive code. Removing it makes *every*
session record unloadable, and the failure is **silent**: `records
generate-descriptions` catches the validation error per record, logs it, and
reports "0 added" — no crash, no obviously wrong output, just nothing generated.

**The bug.** `pytanis.pretalx.models.Submission` has a `model_validator(mode="after")`
called `mangle_submission_type` which *rewrites the field in place*:

```python
self.submission_type_id = getattr(self.submission_type, 'id', None)
self.submission_type   = getattr(self.submission_type, 'name', None)
```

It converts `TransSubmissionType(id=…, name=…)` into just the name. Run once, that
is correct. Run a **second** time on the already-converted value, `getattr(..., 'name')`
finds nothing and returns `None` — so the field is wiped. Because the assignment
happens inside an after-validator, no field validation catches it. The validator
runs again whenever the model is re-validated or the instance is reused, so both
loading a stored record and building a new one from stored data hit it.

**The fix, in three parts** — all are required:

| Part | Location | What it does |
|---|---|---|
| Helper | `unmangle_submission_type()` | Re-nests the flattened value as `{"id": submission_type_id, "name": <value>}` so the validator can unwrap it correctly again |
| Every load | `load_session_record(path)` | Applies the helper before validating. **Use this instead of `SessionRecord.model_validate_json` everywhere** — `add_descriptions`, the YouTube metadata step and the publisher all load records and write them back |
| Fetch path | end of `create_record()` | Serializes the record, then restores `submission_type` / `submission_type_id` from the source data before writing |

The load-side fix is the important one. Fixing only the fetch path is not enough:
any code that loads a record and writes it back persists the null. That is exactly
what happened — after the first repair, `records generate-descriptions` corrupted
every record it touched, one per generated description, and the count of broken
records matched the count of generated texts exactly.

**Repairing corrupted records** without losing generated texts: take
`submission_type` and `submission_type_id` from the raw pytanis dump in
`{work_dir}/{event_slug}/pretalx/{code}.json` and write them into the matching file
under `records/`. Do **not** re-run `records fetch` for this — `create_record`
rebuilds the record with empty `sm_*` fields and would discard the descriptions.

The read-side guard (`isinstance(...) and "name" not in submission_type`) makes the
helper a no-op on already-correct API data. That is why it looks superfluous — it
is not.

**Symptom if it regresses:** `pytube records generate-descriptions` reports
processed records but adds nothing, and `SessionRecord.model_validate_json()` on
`{work_dir}/{event_slug}/records/*.json` raises
`Input should be an object [type=model_type, input_value=None]` for
`pretalx_session.session.submission_type`.

**Side effect to be aware of:** the write path uses `json.dumps(..., ensure_ascii=False)`,
so stored records contain literal UTF-8 (umlauts, em dashes) instead of `\uXXXX`
escapes. The first re-fetch after adopting this therefore produces a large diff.

### Detailed graph of the process

#### Collecting data from Pretalx

The data from Pretalx is collected via the `pythanis` library.

In `/records` the data is stored in JSON files named {pretalx id}.json.

``` mermaid
graph LR;

    P1[Pretalx-API Sessions];
    P2[Pretalx-API Speakers];
    R[(/records)];
    N[NLP Service];
    F((Records));
    P1 & P2 --load_all_confirmed_sessions, load_all_speakers, create_records--> F;
    F --- R;
    F --add_descriptions--> N;
    N --update--> R;    
```

#### Create Video Descriptions

The video descriptions are created from the records.

``` mermaid
graph LR;

    R[(Records)];
    V[(/video_records)];
    V2[(/…_records_updated)];
    F(("PrepareVideo
    Metadata"));
    F --- R;  
    F -- make_all_video_metadata, update_publish_dates --> V;  
    F -- send_all_video_metadata --> V2; 
    V -.move.- V2; 
```
Caveats:  
 - Scheduled videos need to be set 'private' (cannot be 'unlisted').

#### YouTube Check & Notification

The videos have a publishing date set. We need to monitor the release status and trigger Social Media posts
and emails to the speakers.

``` mermaid
graph LR;

    V2[(/…_records_updated)];
    V3[(/video_published)];
    F(("Publisher"));
    VS[YouTube];
    S[(/speaker_to_email)];
    L[(/linked_in_to_post)];
    C{online?};
    F -- check_status --> VS;
    V2 -.move.- V3;
    F -- process_recent_video_releases -> V2; 
    VS --> C --> |prepare_email| S;
    VS --> C --> |prepare_linkedin_post| L;
    VS --> C -.-> |move| V2;
```


In the final step send Social Media posts and emails to the speakers.

``` mermaid
graph LR;

    F(("Publisher"));
    S[(/speaker_to_email)];
    S2[(/speaker_to_email)];
    L[(/linked_in_to_post)];
    L2[(/linked_in_to_post)];
    F -- post_on_linked_id --> L;
    F -- email_speakers --> S;
    S -.move.- S2;
    L -.move.- L2;
    
```
