# GUAF Escalation Queue — production surface

Clinical-crisis escalation queue for the Get Up and Flow production app. The
sorel grading engine signs and POSTs flags to the ingest endpoint; the clinical
lead (Bruce Parsons, MD) triages them from a mobile-first queue at
`/escalations`. Escalation doctrine (triggers, tiers, confidence thresholds,
SLA numbers, business-hours definition) is read entirely from
`backend/escalations/triggers.yaml` — the single source of truth, mirrored from
the ratified spec. No SLA hour or threshold is hardcoded anywhere in the app.

## Endpoints

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/escalations/ingest/` | HMAC-SHA256 (grader) | Ingest a flag. Server recomputes `sla_deadline_at`. |
| `GET` | `/api/escalations/` | Leadership (Admin) | Queue list, ordered tier ASC, `sla_deadline_at` ASC, confidence DESC. `?status=` accepts `open`/`in_review`/`closed` or a raw lifecycle state. |
| `GET` | `/api/escalations/{id}/` | Leadership (Admin) | Full record: client name, evidence spans, audit trail, allowed next states. |
| `POST` | `/api/escalations/{id}/transition/` | Leadership (Admin) | Advance lifecycle. Invalid move → 400 + `allowed_next_states`. |

Leadership auth is the same gate the admin dashboard uses
(`RBACScope.is_admin` → superuser or the `Admin` group).

### SLA rules (from triggers.yaml — server math wins)

- **Tier 1** — 12h, calendar clock, any day (weekends included). Also sends email.
- **Tier 2** — 24 business hours. **Tier 3** — 72 business hours.
- Business hours: Mon–Fri, **America/New_York**; weekends contribute zero. The
  intake day's remaining sliver is not credited — accrual starts at the next
  business day's 00:00. (This is what makes a Friday-evening flag due Tuesday.)
  The YAML declares no intra-day 9–5 window, so a business day supplies its full
  24 hours; inventing a narrower window would be a magic number the brief forbids.

### Lifecycle

```
open → acknowledged → in_review → { escalated_to_clinical | resolved | false_positive }
```

Every transition writes an audited `EscalationTransition` row (actor, from, to,
note, timestamp). The creation row is system-authored (null actor).
`false_positive` records are retained, never deleted. SLA breach is **computed**
(`breached`, `seconds_remaining`), never stored.

## Env vars Brian must set on Render

| Var | Required | Default | Notes |
| --- | --- | --- | --- |
| `GUAF_ESCALATION_INGEST_SECRET` | **Yes** | *(none — fail closed)* | HMAC shared secret. Unset ⇒ every ingest rejected 401. Share the exact value with the sorel grader. |
| `GUAF_ESCALATION_NTFY_TOPIC` | No | `guaf-esc-ddf1fe5ab333` | ntfy topic for queue push. Deliberately **not** the personal `aegis-brian-fischman` topic. |
| `GUAF_CLINICAL_LEAD_EMAIL` | For Tier-1 email | *(none — email skipped, logged loudly)* | Bruce's address for Tier-1 alerts. Uses the existing Postmark/anymail setup (`EMAIL_PROVIDER=postmark`, `POSTMARK_SERVER_TOKEN`). |

`APP_BASE_URL` (already set) is used for the queue link in the Tier-1 email.

## Bruce's ntfy iOS setup

1. Install the **ntfy** app from the App Store.
2. Tap **+** to subscribe to a topic.
3. Topic name: **`guaf-esc-ddf1fe5ab333`** (server `ntfy.sh`, the default).
4. Allow notifications. Tier-1 flags arrive at urgent priority (bypasses quiet
   hours); Tier 2/3 arrive at high priority.

If Brian overrides `GUAF_ESCALATION_NTFY_TOPIC`, Bruce subscribes to that value
instead — keep the two in sync.

## Ingest contract for the sorel grader

- **URL**: `POST https://<api-host>/api/escalations/ingest/`
- **Header**: `X-GUAF-Signature: <hex>` where
  `hex = HMAC_SHA256(GUAF_ESCALATION_INGEST_SECRET, raw_request_body)`.
  A `sha256=` prefix is tolerated. Compare is constant-time; mismatch/absence ⇒ 401.
- **Body** (JSON):

```json
{
  "trigger_id": "suicidal_thought",   // must exist in triggers.yaml
  "tier": 1,                          // 1|2|3, 1 = most severe
  "confidence": 0.87,                 // 0.0–1.0
  "client_ref": "grader-handle-or-name",   // optional free text (pre-linkage)
  "client_id": 42,                    // optional platform user id if known
  "session_ref": "session-123",       // optional
  "evidence": [                       // optional list of spans
    { "quote": "…", "start": 0, "end": 13 }
  ]
}
```

- **Sign the exact bytes you send.** The server recomputes `sla_deadline_at`
  from `tier` + receipt time; any `sla_deadline_at` in the payload is ignored.
- **Response**: `201` with the created escalation (detail shape). `401` bad
  signature; `400` invalid payload (e.g. unknown tier); `503` if triggers.yaml
  fails to load (fail-closed — ingestion refused, never silently degraded).
- **On create**: ntfy push (all tiers) fires on commit; Tier 1 additionally
  emails the clinical lead. Delivery failures are logged loudly and never roll
  back the persisted escalation.

## Resolution & archive

Closing an escalation is a clinical record, not just a status flip. Every close
captures **how** it was handled, stamps who/when, archives the card, and keeps
the whole trail auditable. Reopen is possible but leadership-gated and itself
audited.

### Resolution vocabulary (Bruce edits this — no code change)

`ResolutionMethod` (name, slug, active, sort_order) is the editable list of ways
an escalation can be resolved. It is seeded by a data migration with Bruce's
starting vocabulary — *contacted client; session with client; referred to
therapist/psychiatrist; crisis services engaged; coach guidance; increased
monitoring; no action needed; other* — and then owned entirely through **Django
admin**:

- **Add / rename / reorder**: edit rows under *Escalations → Resolution methods*.
  `sort_order` drives the order methods appear in the close sheet.
- **Retire a method**: uncheck **active**. It vanishes from the close sheet but
  stays intact on every historical audit row that used it (methods are
  `SET_NULL`, never hard-deleted out from under the record).
- The seed migration is idempotent (keyed on slug) — it never duplicates rows or
  clobbers a name leadership has since edited.

### Closing rules

A move into a closing status (`resolved`, `false_positive`,
`escalated_to_clinical`) **requires** a `resolution_method` (by slug). The
`other` method additionally requires a `resolution_note`. On a valid close the
server stamps the escalation with `resolution_method`, `resolution_note`,
`resolved_by`, `resolved_at`, and `archived_at`, and copies the method + note
onto the `EscalationTransition` audit row.

### Archive & filtering

Closing sets `archived_at`. The queue list **excludes archived rows by default**;
`?archived=true` returns only them (the Archive tab). `?status=` still filters by
lifecycle state or group and composes with the archive flag. Archived cards are
read-only — no further transitions — **except** a leadership-only reopen.

### New / changed endpoints

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/escalations/methods/` | Leadership | Active resolution vocabulary (slug + name), in sort order — feeds the close sheet. |
| `GET` | `/api/escalations/?archived=true` | Leadership | Archive view (only `archived_at`-set rows). Default list excludes them. |
| `POST` | `/api/escalations/{id}/transition/` | Leadership | Closing moves now require `resolution_method`; `other` requires `resolution_note`. Missing method → **400** with `resolution_methods` (the list to render). |
| `POST` | `/api/escalations/{id}/reopen/` | Leadership | Reopen an archived escalation → `in_review`. Clears the escalation's resolution fields (the audit trail keeps them) and writes an audit row. Non-archived → 400. |

Transition body gains `resolution_method` (slug) and `resolution_note`. The
detail payload's `transitions` carry `resolution_method_name` /
`resolution_method_slug` / `resolution_note`; the list row carries the closing
summary (`resolution_method_name`, `resolution_note`, `resolved_by_name`,
`resolved_at`, `archived_at`) so an Archive card renders without a detail fetch.

### Frontend (`/escalations`)

- Closing actions open a **mobile bottom-sheet**: single-tap method list, a note
  field (required for *Other*), and a confirm button that names the action
  ("Mark resolved"). Reduced-motion and 44px targets hold.
- New **Archive** tab. Archived cards show the resolution method, note, who, and
  when, plus a leadership **Reopen for review** action.
- Card expand gains a **History** section — the full audited transition trail
  (status → status, actor, timestamp, note), newest first, in quiet type.
