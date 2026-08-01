import { useState } from "react";

import { fetchEscalationDetail, transitionEscalation } from "../api/escalations";
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
    { to: "resolved", label: "Resolve", kind: "ghost" },
    { to: "false_positive", label: "False positive", kind: "ghost" },
    { to: "escalated_to_clinical", label: "Escalate to clinical", kind: "danger" },
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

export function EscalationCard({ escalation, nowMs, polledAtMs, reducedMotion, onChanged }) {
  const [expanded, setExpanded] = useState(false);
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const tier = escalation.tier;
  const color = tierColor(tier);
  const meta = TIER_META[tier] || TIER_META[3];

  // Countdown ticks against the live clock; under reduced motion the burn line
  // holds the fraction from the last poll (static, no per-second motion).
  const seconds = liveSecondsRemaining(escalation.sla_deadline_at, nowMs);
  const countdown = formatCountdown(seconds);
  const breached = seconds <= 0;
  // The burn line depletes with the live clock. Under reduced motion it holds
  // the fraction from the last 60s poll (static — no per-second motion).
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

  async function act(toStatus) {
    setBusy(true);
    setError("");
    try {
      await transitionEscalation(escalation.id, toStatus);
      await onChanged();
    } catch (err) {
      const allowed = err?.response?.data?.allowed_next_states;
      setError(
        allowed
          ? `That step isn't available now. Allowed: ${allowed.map((s) => STATUS_LABELS[s] || s).join(", ") || "none"}.`
          : "That action didn't go through. Check your connection and try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  const actions = NEXT_ACTIONS[escalation.status] || [];

  return (
    <article
      className="esc-card"
      data-breached={breached}
      style={{ "--esc-tier-color": color }}
    >
      <div className="esc-burn" aria-hidden="true">
        {!breached && (
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

        <div className="esc-countdown-row">
          <span className="esc-countdown" data-breached={breached}>
            {countdown.text}
          </span>
          <span className="esc-countdown-label">
            {breached ? `overdue · ${meta.sla}` : `until due · ${meta.sla}`}
          </span>
        </div>

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

            {actions.length > 0 ? (
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
                    onClick={() => act(a.to)}
                  >
                    {a.label}
                  </button>
                ))}
              </div>
            ) : (
              <p className="esc-meta-line">No further action — this escalation is closed.</p>
            )}

            {error && <p className="esc-action-error">{error}</p>}
          </div>
        )}
      </div>
    </article>
  );
}
