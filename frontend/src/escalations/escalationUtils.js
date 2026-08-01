import { useEffect, useState } from "react";

// Tier presentation. Colors mirror escalations.css tokens; the label is the
// plain clinical register the copy calls for.
export const TIER_META = {
  1: { color: "#c6402e", label: "Tier 1", sla: "12h, any day" },
  2: { color: "#c98a1b", label: "Tier 2", sla: "24 business hours" },
  3: { color: "#4a6b8a", label: "Tier 3", sla: "72 business hours" },
};

export function tierColor(tier) {
  return (TIER_META[tier] || TIER_META[3]).color;
}

// Format a signed seconds count as a live countdown. Breached reads "overdue".
export function formatCountdown(secondsRemaining) {
  if (secondsRemaining <= 0) {
    return { text: formatDuration(-secondsRemaining), overdue: true };
  }
  return { text: formatDuration(secondsRemaining), overdue: false };
}

function formatDuration(totalSeconds) {
  const s = Math.max(0, Math.floor(totalSeconds));
  const days = Math.floor(s / 86400);
  const hours = Math.floor((s % 86400) / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  const seconds = s % 60;
  if (days > 0) {
    return `${days}d ${String(hours).padStart(2, "0")}h ${String(minutes).padStart(2, "0")}m`;
  }
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

// Fraction of the SLA window still remaining, in [0, 1]. Drives the burn line.
export function burnFraction(createdAt, deadlineAt, nowMs) {
  const created = new Date(createdAt).getTime();
  const deadline = new Date(deadlineAt).getTime();
  const total = deadline - created;
  if (!Number.isFinite(total) || total <= 0) {
    return nowMs >= deadline ? 0 : 1;
  }
  const remaining = deadline - nowMs;
  return Math.max(0, Math.min(1, remaining / total));
}

// Seconds remaining recomputed against the live clock, so the countdown ticks
// between the server's 60s snapshots rather than freezing on the polled value.
export function liveSecondsRemaining(deadlineAt, nowMs) {
  return Math.round((new Date(deadlineAt).getTime() - nowMs) / 1000);
}

export function useReducedMotion() {
  const [reduced, setReduced] = useState(() =>
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches,
  );
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!mq) return undefined;
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener?.("change", onChange);
    return () => mq.removeEventListener?.("change", onChange);
  }, []);
  return reduced;
}
