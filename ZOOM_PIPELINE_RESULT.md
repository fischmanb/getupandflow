# Zoom Transcript Pipeline

Production-first pipeline that turns Zoom cloud recordings into stored,
consent-gated coaching-session transcripts and exposes them for outbound pull
by the grading engine (sorel). Safety-critical storage never depends on sorel:
Zoom pushes → we store; sorel pulls on its own schedule.

Backend app: `backend/transcripts/`. The meeting lifecycle (create/update/delete
Zoom meetings, `auto_recording: "cloud"`) already lives in `planner` and is
unchanged here.

## Data flow

```
Zoom meeting ends
  → cloud recording + transcript (VTT) generated
  → Zoom POSTs recording.completed (and/or recording.transcript_completed)
      to  https://api.getupandflow.co/api/zoom/webhook/
  → we verify the v0 signature, match the Event by zoom_meeting_id,
    check the client's recording consent, download the VTT with an S2S token,
    parse it, and write a Transcript row + the raw VTT to R2.
  → sorel polls  GET /api/transcripts/feed/?since=<iso>  (HMAC-signed)
    and grades each transcript out-of-band.
```

If the transcript file isn't materialized yet (download 404s), we poll **once**
more after a short delay (`ZOOM_TRANSCRIPT_RETRY_DELAY_SECONDS`, default 90s) via
a one-shot daemon thread — no new daemon/queue process. Zoom also frequently
delivers the VTT on a later `recording.transcript_completed` event, which we
handle identically.

## Environment variables

### Zoom Server-to-Server OAuth (meeting lifecycle + recording download)
| Var | Purpose |
| --- | --- |
| `ZOOM_ACCOUNT_ID` | S2S OAuth account id |
| `ZOOM_CLIENT_ID` | S2S OAuth client id |
| `ZOOM_CLIENT_SECRET` | S2S OAuth client secret |

Absent Zoom credentials never fail an event write or crash a webhook — Zoom
work is failure-soft throughout.

### Zoom webhook
| Var | Purpose |
| --- | --- |
| `ZOOM_WEBHOOK_SECRET_TOKEN` | Secret Token from the app's Event Subscriptions page. Used for BOTH the endpoint-URL validation challenge and per-event v0 signature verification. **Fail closed**: if unset, the validation challenge is refused (503) and every event is rejected (401). |
| `ZOOM_SIGNATURE_MAX_SKEW_SECONDS` | (optional) Replay window for the signed request timestamp. Default 300 (5 min, Zoom's recommendation). |
| `ZOOM_TRANSCRIPT_RETRY_DELAY_SECONDS` | (optional) Delay before the poll-once retry on a 404 download. Default 90. |

### Transcript storage (Cloudflare R2 — reuses the existing photo bucket config)
| Var | Purpose |
| --- | --- |
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` | R2 S3-compatible credentials. Raw VTTs land under the `transcripts/` prefix. Without them the app falls back to local `FileSystemStorage` (dev only). |

### Feed for sorel
| Var | Purpose |
| --- | --- |
| `GUAF_ESCALATION_INGEST_SECRET` | The **existing** shared machine secret (same one the escalations ingest uses — one secret per machine boundary). Used to HMAC-sign feed requests. **Fail closed**: if unset, the feed rejects every request (401). |
| `GUAF_TRANSCRIPT_FEED_PAGE_SIZE` | (optional) Feed page size. Default 50. |

## Consent gate

A transcript is stored **only** for a client whose profile carries recording
consent: `accounts.UserProfile.recording_consent` (BooleanField, default True).
Clients accept ToS + Privacy — which covers session recording — at signup, so
the field defaults True and migration `accounts/0008` backfills existing
terms-accepted rows to True. The field exists so consent can be **revoked**: a
revoked client's webhook is authenticated, acknowledged (200), and logged, but
**nothing is stored** and the VTT is never even downloaded.

## Zoom App Marketplace dashboard steps (Brian performs)

In the Zoom App Marketplace, on the **Server-to-Server OAuth** app that already
backs meeting creation:

1. **Scopes** — ensure these are granted:
   - `meeting:write:admin` / `meeting:read:admin` (already present for lifecycle)
   - `cloud_recording:read:admin` (a.k.a. `recording:read:admin`) — needed to
     download the transcript VTT with the S2S token.
2. **Feature → Event Subscriptions** — enable event notifications:
   - **Event notification endpoint URL:** `https://api.getupandflow.co/api/zoom/webhook/`
   - Copy the **Secret Token** into the `ZOOM_WEBHOOK_SECRET_TOKEN` env var, then
     click **Validate** (our endpoint answers the challenge automatically).
   - Subscribe to events:
     - **Recording → All Recordings have completed** (`recording.completed`)
     - **Recording → Recording Transcript files have completed**
       (`recording.transcript_completed`)
   - (Recommended) enable **"Include download token"** so the webhook carries a
     short-lived `download_token`; we use it when present and fall back to the
     S2S access token otherwise.
3. Confirm meetings are created with `auto_recording: "cloud"` (they are — this
   is unchanged).

## Feed contract (for sorel)

```
GET https://api.getupandflow.co/api/transcripts/feed/?since=<iso8601>
Headers:
  X-GUAF-Signature: <hex HMAC-SHA256(GUAF_ESCALATION_INGEST_SECRET, RAW_QUERY_STRING)>
```

- **Auth:** HMAC-SHA256 of the **raw query string** (everything after `?`, or the
  empty string when there is no query), hex-encoded, in `X-GUAF-Signature`. An
  optional `sha256=` prefix is tolerated. Constant-time compare; fail closed.
- **`since`** (optional): ISO 8601 datetime; **exclusive** high-water mark on
  `created_at`. Pass the `created_at` of the last transcript you ingested to page
  forward without duplicates. Naive datetimes are treated as UTC.
- **Ordering:** `created_at` ascending, then `id`.
- **Pagination:** page-number (`?page=`, `?page_size=`); response carries
  `count`, `next`, `previous`, `page_size`, `total_pages`, `results`.

Each result row:

| Field | Notes |
| --- | --- |
| `id` | Transcript id |
| `event_id` | Source `planner.Event` id (nullable if the event was deleted) |
| `client_id` | The client the session was for |
| `coach_id` | The coach who ran it |
| `zoom_meeting_id` | Matches `Event.zoom_meeting_id` |
| `occurred_at` | The **meeting's** start datetime (never ingest time) |
| `duration_s` | Session length in seconds (from the VTT's last cue) |
| `grading_status` | `pending` \| `graded` \| `failed` (starts `pending`) |
| `plain_text` | Speaker-tagged extracted transcript text |
| `created_at` | When we ingested it (feed ordering / `since` cursor) |

The raw VTT is **not** inlined in the feed — consumers grade from `plain_text`;
the file lives in R2.

## Tests

`backend/transcripts/tests.py` (22 tests, all mocked — no network, no real
storage backend):

- URL-validation challenge (correct encrypted token; 503 when secret unset)
- v0 signature: accept, reject bad, reject missing, reject stale timestamp
- `recording.completed` → Transcript row with correct `occurred_at` (meeting
  start), R2/storage write round-trip, parsed speaker-tagged text + duration,
  download authorized with the webhook's download token
- consent-revoked → acknowledged, not stored, no download
- no matching event → skipped
- redelivery idempotency (unique `zoom_meeting_id`)
- download 404 → poll-once deferred retry scheduled; retry does not re-loop
- transcript delivered on a later `recording.transcript_completed` event
- feed: HMAC accept/reject/missing, `since` exclusive filtering, invalid `since`
- VTT parsing and storage-selection units
