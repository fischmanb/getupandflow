import { useState } from "react";

import {
  fetchEscalationDetail,
  reopenEscalation,
  transitionEscalation,
} from "../api/escalations";
import {
  TIER_META,
  burnFraction,
  formatCountdown,
  liveSecondsRemaining,
  tierColor,
} from "./escalationUtils";

// The action row is the lifecycle graph in thumb-reach form:
//   open        -> Acknowledge
//   acknowledged-> Start review
//   in_review   -> Resolve · False positive · Escalate to clinical
const NEXT_ACTIONS = {
  open: [{ to: "acknowledged", label: "Acknowledge", kind: "solid" }],
  acknowledged: [{ to: "in_review", label: "Start review", kind: "solid" }],
  in_review: [
    { to: "resolved", label: "Resolve", kind: "ghost", closing: true },
    { to: "false_positive", label: "False positive", kind: "ghost", closing: true },
    { to: "escalated_to_clinical", label: "Escalate to clinical", kind: "danger", closing: true },
  ],
};

const STATUS_LABELS = {
  open: "Open",
  acknowledged: "Acknowledged",
  in_review: "In review",
  escalated_to_clinical: "Escalated to clinical",
  resolved: "Resolved",
  false_positive: "False positive",
};

// The confirm button in the close sheet names the action it commits.
const CONFIRM_LABEL = {
  resolved: "Mark resolved",
  false_positive: "Mark false positive",
  escalated_to_clinical: "Escalate to clinical",
};

const OTHER_SLUG = "other";

function formatWhen(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function EscalationCard({ escalation, methods, nowMs, polledAtMs, reducedMotion, onChanged }) {
  const [expanded, setExpanded] = useState(false);
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // Close sheet state: the pending closing action, the chosen method, its note.
  const [sheetAction, setSheetAction] = useState(null); // { to, label }
  const [chosenMethod, setChosenMethod] = useState(null); // slug
  const [note, setNote] = useState("");

  const tier = escalation.tier;
  const color = tierColor(tier);
  const meta = TIER_META[tier] || TIER_META[3];
  const archived = Boolean(escalation.archived_at);

  // Countdown ticks against the live clock; under reduced motion the burn line
  // holds the fraction from the last poll (static, no per-second motion).
  const seconds = liveSecondsRemaining(escalation.sla_deadline_at, nowMs);
  const countdown = formatCountdown(seconds);
  const breached = seconds <= 0;
  const burnClock = reducedMotion ? polledAtMs : nowMs;
  const burnPct = Math.round(
    burnFraction(escalation.created_at, escalation.sla_deadline_at, burnClock) * 100,
  );

  async function toggleExpand() {
    const next = !expanded;
    setExpanded(next);
    if (next && !detail) {
      try {
        setDetail(await fetchEscalationDetail(escalation.id));
      } catch {
        setError("Couldn't load the full record. Pull to refresh and try again.");
      }
    }
  }

  // Immediate (non-closing) lifecycle move — acknowledge, start review.
  async function act(toStatus) {
    setBusy(true);
    setError("");
    try {
      await transitionEscalation(escalation.id, toStatus);
      await onChanged();
    } catch (err) {
      setError(transitionError(err));
    } finally {
      setBusy(false);
    }
  }

  function openSheet(action) {
    setSheetAction(action);
    setChosenMethod(null);
    setNote("");
    setError("");
  }

  function closeSheet() {
    setSheetAction(null);
    setChosenMethod(null);
    setNote("");
  }

  const noteRequired = chosenMethod === OTHER_SLUG;
  const canConfirm =
    Boolean(chosenMethod) && (!noteRequired || note.trim().length > 0);

  async function confirmClose() {
    if (!canConfirm || !sheetAction) return;
    setBusy(true);
    setError("");
    try {
      await transitionEscalation(escalation.id, sheetAction.to, {
        resolutionMethod: chosenMethod,
        resolutionNote: note.trim(),
      });
      closeSheet();
      await onChanged();
    } catch (err) {
      setError(transitionError(err));
    } finally {
      setBusy(false);
    }
  }

  async function reopen() {
    setBusy(true);
    setError("");
    try {
      await reopenEscalation(escalation.id);
      await onChanged();
    } catch {
      setError("Couldn't reopen this escalation. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  const actions = NEXT_ACTIONS[escalation.status] || [];
  const trail = detail?.transitions ? [...detail.transitions].reverse() : [];

  return (
    <article
      className="esc-card"
      data-breached={breached}
      data-archived={archived}
      style={{ "--esc-tier-color": color }}
    >
      <div className="esc-burn" aria-hidden="true">
        {!breached && !archived && (
          <div className="esc-burn-fill" style={{ width: `${burnPct}%` }} />
        )}
      </div>

      <div className="esc-card-body">
        <div className="esc-card-top">
          <span className="esc-chip">{meta.label}</span>
          <span className="esc-initials" title="Initials only — tap to expand for the full name">
            {escalation.client_initials}
          </span>
          <span className="esc-confidence">
            {Math.round(escalation.confidence * 100)}% confidence
          </span>
        </div>

        <p className="esc-trigger">{escalation.trigger_label}</p>

        {archived ? (
          <p className="esc-status-line">
            {STATUS_LABELS[escalation.status] || escalation.status}
            {escalation.resolution_method_name ? ` · ${escalation.resolution_method_name}` : ""}
          </p>
        ) : (
          <div className="esc-countdown-row">
            <span className="esc-countdown" data-breached={breached}>
              {countdown.text}
            </span>
            <span className="esc-countdown-label">
              {breached ? `overdue · ${meta.sla}` : `until due · ${meta.sla}`}
            </span>
          </div>
        )}

        <button className="esc-expand-toggle" onClick={toggleExpand} aria-expanded={expanded}>
          {expanded ? "Hide details" : "Show details"}
        </button>

        {expanded && (
          <div className="esc-detail">
            <p className="esc-detail-name">
              {detail ? detail.client_name : "Loading…"}
            </p>
            {detail?.evidence?.length > 0 && (
              <ul className="esc-evidence">
                {detail.evidence.map((span, i) => (
                  <li key={i}>{typeof span === "string" ? span : span.quote || JSON.stringify(span)}</li>
                ))}
              </ul>
            )}
            {detail?.session_ref && (
              <p className="esc-meta-line">Session: {detail.session_ref}</p>
            )}
            <p className="esc-meta-line">Status: {STATUS_LABELS[escalation.status] || escalation.status}</p>

            {/* Archived: the resolution record — method, note, who, when. */}
            {archived && (
              <div className="esc-resolution">
                <p className="esc-resolution-title">Resolution</p>
                <p className="esc-resolution-method">
                  {escalation.resolution_method_name || "—"}
                </p>
                {escalation.resolution_note && (
                  <p className="esc-resolution-note">“{escalation.resolution_note}”</p>
                )}
                <p className="esc-meta-line">
                  {escalation.resolved_by_name || "Unknown"}
                  {escalation.resolved_at ? ` · ${formatWhen(escalation.resolved_at)}` : ""}
                </p>
              </div>
            )}

            {/* Live: thumb-reach actions. Closing actions open the sheet. */}
            {!archived && actions.length > 0 && (
              <div className="esc-actions">
                {actions.map((a) => (
                  <button
                    key={a.to}
                    className={
                      "esc-card-action" +
                      (a.kind === "ghost" ? " esc-card-action--ghost" : "") +
                      (a.kind === "danger" ? " esc-card-action--danger" : "")
                    }
                    disabled={busy}
                    onClick={() => (a.closing ? openSheet(a) : act(a.to))}
                  >
                    {a.label}
                  </button>
                ))}
              </div>
            )}

            {/* History — the full audited trail, newest first, quiet type. */}
            {trail.length > 0 && (
              <div className="esc-history">
                <p className="esc-history-title">History</p>
                <ol className="esc-history-list">
                  {trail.map((t) => (
                    <li key={t.id} className="esc-history-item">
                      <span className="esc-history-move">
                        {t.from_status ? `${STATUS_LABELS[t.from_status] || t.from_status} → ` : ""}
                        {STATUS_LABELS[t.to_status] || t.to_status}
                      </span>
                      <span className="esc-history-meta">
                        {(t.actor_username || "system")}
                        {" · "}
                        {formatWhen(t.created_at)}
                      </span>
                      {t.resolution_method_name && (
                        <span className="esc-history-detail">{t.resolution_method_name}</span>
                      )}
                      {(t.resolution_note || t.note) && (
                        <span className="esc-history-detail">
                          {t.resolution_note || t.note}
                        </span>
                      )}
                    </li>
                  ))}
                </ol>
              </div>
            )}

            {/* Archived cards are read-only except a leadership-only reopen. */}
            {archived && (
              <button className="esc-reopen" disabled={busy} onClick={reopen}>
                Reopen for review
              </button>
            )}

            {error && <p className="esc-action-error">{error}</p>}
          </div>
        )}
      </div>

      {/* ── Close sheet ─────────────────────────────────────────────────── */}
      {sheetAction && (
        <div className="esc-sheet-backdrop" onClick={closeSheet}>
          <div
            className="esc-sheet"
            role="dialog"
            aria-modal="true"
            aria-label={CONFIRM_LABEL[sheetAction.to] || sheetAction.label}
            onClick={(e) => e.stopPropagation()}
          >
            <p className="esc-sheet-title">{CONFIRM_LABEL[sheetAction.to] || sheetAction.label}</p>
            <p className="esc-sheet-sub">How was this handled? Pick one.</p>

            <div className="esc-method-list">
              {methods.map((m) => (
                <button
                  key={m.slug}
                  className="esc-method"
                  aria-pressed={chosenMethod === m.slug}
                  onClick={() => setChosenMethod(m.slug)}
                >
                  {m.name}
                </button>
              ))}
            </div>

            <label className="esc-note-label">
              {noteRequired ? "Note (required for Other)" : "Note (optional)"}
              <textarea
                className="esc-note-field"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={3}
                placeholder={noteRequired ? "Describe what was done." : "Add context if useful."}
              />
            </label>

            {error && <p className="esc-action-error">{error}</p>}

            <div className="esc-sheet-actions">
              <button className="esc-sheet-cancel" onClick={closeSheet} disabled={busy}>
                Cancel
              </button>
              <button
                className="esc-sheet-confirm"
                onClick={confirmClose}
                disabled={busy || !canConfirm}
              >
                {CONFIRM_LABEL[sheetAction.to] || "Confirm"}
              </button>
            </div>
          </div>
        </div>
      )}
    </article>
  );
}

function transitionError(err) {
  const allowed = err?.response?.data?.allowed_next_states;
  if (allowed) {
    return `That step isn't available now. Allowed: ${allowed.map((s) => STATUS_LABELS[s] || s).join(", ") || "none"}.`;
  }
  const detail = err?.response?.data?.detail;
  if (detail) return detail;
  return "That action didn't go through. Check your connection and try again.";
}
