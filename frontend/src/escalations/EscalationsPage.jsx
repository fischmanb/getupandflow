import { useCallback, useEffect, useRef, useState } from "react";

import { fetchEscalations, fetchResolutionMethods } from "../api/escalations";
import { EscalationCard } from "./EscalationCard";
import { useReducedMotion } from "./escalationUtils";
import "./escalations.css";

const FILTERS = [
  { key: "open", label: "Open" },
  { key: "in_review", label: "In review" },
  { key: "archive", label: "Archive" },
];

const EMPTY_COPY = {
  open: "No open escalations.",
  in_review: "Nothing in review.",
  archive: "Nothing archived yet.",
};

const POLL_MS = 60000; // 60s refresh — a between-sessions cadence, not a firehose.

export function EscalationsPage() {
  const [filter, setFilter] = useState("open");
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("loading"); // loading | ready | error
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [polledAtMs, setPolledAtMs] = useState(() => Date.now());
  const [methods, setMethods] = useState([]);
  const reducedMotion = useReducedMotion();
  const filterRef = useRef(filter);
  filterRef.current = filter;

  const load = useCallback(async (activeFilter, { silent } = {}) => {
    if (!silent) setStatus("loading");
    try {
      const data = await fetchEscalations(activeFilter);
      // Ignore a response for a filter the user has since switched away from.
      if (filterRef.current !== activeFilter) return;
      setItems(data);
      setPolledAtMs(Date.now());
      setStatus("ready");
    } catch {
      if (filterRef.current === activeFilter) setStatus("error");
    }
  }, []);

  // Reload on filter change.
  useEffect(() => {
    load(filter);
  }, [filter, load]);

  // The resolution vocabulary — loaded once for the close sheet. It's small and
  // rarely changes (leadership edits it in admin).
  useEffect(() => {
    fetchResolutionMethods().then(setMethods).catch(() => setMethods([]));
  }, []);

  // 60s background poll (silent — no loading flash).
  useEffect(() => {
    const id = setInterval(() => load(filterRef.current, { silent: true }), POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  // 1s tick drives the countdowns + burn lines.
  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="esc-root">
      <header className="esc-header">
        <p className="esc-eyebrow">Get Up and Flow · Clinical</p>
        <h1 className="esc-title">Escalation queue</h1>
        <p className="esc-subtitle">What needs review now, most severe first.</p>
      </header>

      <nav className="esc-filter" aria-label="Filter by status">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            className="esc-filter-tab"
            aria-pressed={filter === f.key}
            onClick={() => setFilter(f.key)}
          >
            {f.label}
          </button>
        ))}
      </nav>

      <main className="esc-shell">
        {status === "loading" && (
          <div className="esc-notice">Loading the queue…</div>
        )}

        {status === "error" && (
          <div className="esc-notice">
            <p className="esc-notice-title">Couldn't load the queue</p>
            <p>Check your connection. The queue refreshes on its own, or retry now.</p>
            <button className="esc-retry" onClick={() => load(filter)}>Retry</button>
          </div>
        )}

        {status === "ready" && items.length === 0 && (
          <div className="esc-notice">
            <p className="esc-notice-title">{EMPTY_COPY[filter]}</p>
            <p>You're all clear here.</p>
          </div>
        )}

        {status === "ready" && items.length > 0 && (
          <>
            <div className="esc-list">
              {items.map((esc) => (
                <EscalationCard
                  key={esc.id}
                  escalation={esc}
                  methods={methods}
                  nowMs={nowMs}
                  polledAtMs={polledAtMs}
                  reducedMotion={reducedMotion}
                  onChanged={() => load(filterRef.current, { silent: true })}
                />
              ))}
            </div>
            <p className="esc-updated">
              Updated {new Date(polledAtMs).toLocaleTimeString()} · refreshes every 60s
            </p>
          </>
        )}
      </main>
    </div>
  );
}
