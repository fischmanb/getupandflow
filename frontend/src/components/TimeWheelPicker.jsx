import { useEffect, useMemo, useRef } from "react";

/**
 * TimeWheelPicker
 *
 * Three scrollable columns: hour (1-12), minute (00, 15, 30, 45), period (AM/PM).
 * Wheel-of-fortune style: items snap-scroll vertically, current selection lives in
 * the highlighted center row.
 *
 * Value is a 24-hour "HH:MM" string. onChange emits the same.
 * onCommit fires when the user lets go after scrolling, useful for committing only
 * when settled (not on every micro-scroll event).
 */

const HOURS = Array.from({ length: 12 }, (_, i) => i + 1); // 1..12
const MINUTES = ["00", "15", "30", "45"];
const PERIODS = ["AM", "PM"];

const ITEM_HEIGHT = 36; // px — matches CSS

function parse24h(value) {
  if (!value) return { hour12: 9, minute: "00", period: "AM" };
  const [hStr, mStr] = value.split(":");
  const h24 = Number(hStr);
  const minute = mStr || "00";
  // Snap minute to nearest preset for the wheel (15-min increments).
  const snappedMinute = MINUTES.reduce((closest, m) => {
    return Math.abs(Number(m) - Number(minute)) < Math.abs(Number(closest) - Number(minute)) ? m : closest;
  }, MINUTES[0]);
  const period = h24 >= 12 ? "PM" : "AM";
  const hour12 = h24 % 12 === 0 ? 12 : h24 % 12;
  return { hour12, minute: snappedMinute, period };
}

function format24h(hour12, minute, period) {
  let h24 = hour12 % 12;
  if (period === "PM") h24 += 12;
  return `${String(h24).padStart(2, "0")}:${minute}`;
}

function Column({ items, value, onChange, ariaLabel }) {
  const ref = useRef(null);
  const valueIndex = useMemo(() => items.findIndex((it) => String(it) === String(value)), [items, value]);
  const scrollDebounceRef = useRef(null);

  // Programmatically scroll to the selected item when value changes externally.
  useEffect(() => {
    const el = ref.current;
    if (!el || valueIndex < 0) return;
    el.scrollTo({ top: valueIndex * ITEM_HEIGHT, behavior: "auto" });
  }, [valueIndex]);

  function handleScroll() {
    if (scrollDebounceRef.current) clearTimeout(scrollDebounceRef.current);
    scrollDebounceRef.current = setTimeout(() => {
      const el = ref.current;
      if (!el) return;
      const index = Math.round(el.scrollTop / ITEM_HEIGHT);
      const clamped = Math.max(0, Math.min(items.length - 1, index));
      const next = items[clamped];
      if (String(next) !== String(value)) onChange(next);
      // Snap precisely after settle.
      el.scrollTo({ top: clamped * ITEM_HEIGHT, behavior: "smooth" });
    }, 120);
  }

  return (
    <div className="time-wheel-column" aria-label={ariaLabel} role="listbox">
      <div className="time-wheel-fade time-wheel-fade-top" aria-hidden />
      <div className="time-wheel-fade time-wheel-fade-bottom" aria-hidden />
      <div className="time-wheel-highlight" aria-hidden />
      <div className="time-wheel-scroll" ref={ref} onScroll={handleScroll}>
        <div className="time-wheel-spacer" />
        {items.map((item) => (
          <button
            key={item}
            type="button"
            className={String(item) === String(value) ? "time-wheel-item active" : "time-wheel-item"}
            onClick={() => onChange(item)}
            role="option"
            aria-selected={String(item) === String(value)}
          >
            {item}
          </button>
        ))}
        <div className="time-wheel-spacer" />
      </div>
    </div>
  );
}

export function TimeWheelPicker({ value, onChange, label }) {
  const { hour12, minute, period } = useMemo(() => parse24h(value), [value]);

  function update(nextHour12, nextMinute, nextPeriod) {
    const next = format24h(nextHour12, nextMinute, nextPeriod);
    if (next !== value) onChange(next);
  }

  return (
    <div className="time-wheel-picker" aria-label={label}>
      <Column
        items={HOURS}
        value={hour12}
        onChange={(h) => update(h, minute, period)}
        ariaLabel="Hour"
      />
      <span className="time-wheel-colon">:</span>
      <Column
        items={MINUTES}
        value={minute}
        onChange={(m) => update(hour12, m, period)}
        ariaLabel="Minute"
      />
      <Column
        items={PERIODS}
        value={period}
        onChange={(p) => update(hour12, minute, p)}
        ariaLabel="Period"
      />
    </div>
  );
}

/**
 * DurationWheelPicker
 *
 * Two scrollable columns: hours (0-8), minutes (00, 15, 30, 45). Value is total
 * minutes (integer). onChange emits the same.
 */

const DURATION_HOURS = Array.from({ length: 9 }, (_, i) => i); // 0..8

function parseDurationMinutes(totalMinutes) {
  const clamped = Math.max(0, Math.min(8 * 60 + 45, Number(totalMinutes) || 0));
  const h = Math.floor(clamped / 60);
  const rawMin = clamped % 60;
  const snappedMin = MINUTES.reduce((closest, m) => {
    return Math.abs(Number(m) - rawMin) < Math.abs(Number(closest) - rawMin) ? m : closest;
  }, MINUTES[0]);
  return { hours: h, minute: snappedMin };
}

export function DurationWheelPicker({ value, onChange, label }) {
  const { hours, minute } = useMemo(() => parseDurationMinutes(value), [value]);

  function update(nextHours, nextMinute) {
    const next = nextHours * 60 + Number(nextMinute);
    if (next !== value) onChange(next);
  }

  return (
    <div className="time-wheel-picker" aria-label={label}>
      <Column
        items={DURATION_HOURS}
        value={hours}
        onChange={(h) => update(h, minute)}
        ariaLabel="Duration hours"
      />
      <span className="time-wheel-colon">:</span>
      <Column
        items={MINUTES}
        value={minute}
        onChange={(m) => update(hours, m)}
        ariaLabel="Duration minutes"
      />
    </div>
  );
}
