import { useEffect, useMemo, useRef, useState } from "react";

import { useOutsideClick } from "../hooks/useOutsideClick";

/**
 * TimeDropdown — Google-Calendar-style time picker.
 *
 * Renders a chip showing the current time. Clicking it opens a vertical
 * scrollable list of 15-min increments. Picking one closes the list.
 *
 * If `anchorTime` is provided (used for the End picker), each option in the
 * list also shows the duration from anchor to that time (e.g. "+30 min").
 */

const ITEM_HEIGHT = 36; // px — keep in sync with CSS

function pad(n) {
  return String(n).padStart(2, "0");
}

function format12h(minutes) {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  const period = h >= 12 ? "pm" : "am";
  const displayH = h % 12 === 0 ? 12 : h % 12;
  return `${displayH}:${pad(m)}${period}`;
}

function parseHHMM(value) {
  if (!value) return 0;
  const [h, m] = value.split(":").map(Number);
  return h * 60 + m;
}

function toHHMM(minutes) {
  const wrapped = ((minutes % (24 * 60)) + 24 * 60) % (24 * 60);
  return `${pad(Math.floor(wrapped / 60))}:${pad(wrapped % 60)}`;
}

function formatDurationShort(minutes) {
  if (minutes <= 0) return "";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m} min`;
  if (m === 0) return `${h} hr`;
  return `${h} hr ${m} min`;
}

// Generate every 15-min increment across 24 hours as an array of total-minutes ints.
const ALL_TIMES = Array.from({ length: 96 }, (_, i) => i * 15);

export function TimeDropdown({ value, onChange, anchorTime, ariaLabel }) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef(null);
  const listRef = useRef(null);
  const currentMinutes = useMemo(() => parseHHMM(value), [value]);

  useOutsideClick(containerRef, () => setIsOpen(false), isOpen);

  // When the list opens, scroll so the current value is visible near the top.
  useEffect(() => {
    if (!isOpen) return;
    const el = listRef.current;
    if (!el) return;
    const index = ALL_TIMES.findIndex((m) => m === currentMinutes);
    const targetIndex = index >= 0 ? index : Math.floor(currentMinutes / 15);
    // Center the current item in the visible list (~3 items above).
    const offset = Math.max(0, (targetIndex - 2) * ITEM_HEIGHT);
    el.scrollTop = offset;
  }, [isOpen, currentMinutes]);

  function pick(minutes) {
    onChange(toHHMM(minutes));
    setIsOpen(false);
  }

  return (
    <div className="time-dropdown" ref={containerRef}>
      <button
        type="button"
        className="time-dropdown-chip"
        onClick={() => setIsOpen((v) => !v)}
        aria-label={ariaLabel}
        aria-expanded={isOpen}
      >
        {format12h(currentMinutes)}
      </button>
      {isOpen ? (
        <div className="time-dropdown-list" ref={listRef} role="listbox">
          {ALL_TIMES.map((m) => {
            const isActive = m === currentMinutes;
            // For the End picker, derive duration from anchor (the start time).
            let durationLabel = "";
            if (anchorTime != null) {
              let diff = m - anchorTime;
              if (diff < 0) diff += 24 * 60;
              durationLabel = formatDurationShort(diff);
            }
            return (
              <button
                key={m}
                type="button"
                className={isActive ? "time-dropdown-item active" : "time-dropdown-item"}
                onClick={() => pick(m)}
                role="option"
                aria-selected={isActive}
              >
                <span>{format12h(m)}</span>
                {durationLabel ? <span className="time-dropdown-duration">{durationLabel}</span> : null}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

// Helper exposed for the popover to display in the chip.
export function deriveDuration(startHHMM, endHHMM) {
  const s = parseHHMM(startHHMM);
  const e = parseHHMM(endHHMM);
  let diff = e - s;
  if (diff < 0) diff += 24 * 60;
  return diff;
}

export { format12h, formatDurationShort };
