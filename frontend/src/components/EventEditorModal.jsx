import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { apiClient } from "../api/client";
import { fetchAllPages, getErrorMessage } from "../api/utils";
import { useAuth } from "../auth/AuthContext";
import { useClientFilter } from "../filters/ClientFilterContext";
import { dateToISODate, dateToISOTime } from "../calendar/eventAdapter";

/**
 * Center-screen modal for creating or editing an event. Modeled after Google
 * Calendar's editor: title row, time row (date + start time chip + end time chip),
 * category, optional Location/Description/Repeats, then Save.
 *
 * Props:
 *  - mode: "create" | "edit"
 *  - initialStart, initialEnd: Date objects (always required)
 *  - event: the API event object if editing
 *  - onClose(): close without saving
 *  - onSaved(): close and refresh parent's events
 */

function pad(n) { return String(n).padStart(2, "0"); }

function format12h(date) {
  let h = date.getHours();
  const m = date.getMinutes();
  const period = h >= 12 ? "pm" : "am";
  h = h % 12 === 0 ? 12 : h % 12;
  return `${h}:${pad(m)}${period}`;
}

function formatLongDate(date) {
  return date.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
}

// Generate 15-min increments. If `startFrom` is given (end-time picker),
// list times from startFrom + 15min through end of day, so the end options
// are always *after* the start. Otherwise list the full day from midnight.
function generateDayTimes(anchorDate, startFrom) {
  const out = [];
  if (startFrom) {
    const begin = new Date(startFrom);
    // First option is 15 minutes after the start time.
    begin.setMinutes(begin.getMinutes() + 15, 0, 0);
    const endOfDay = new Date(anchorDate);
    endOfDay.setHours(23, 45, 0, 0);
    const cursor = new Date(begin);
    while (cursor <= endOfDay) {
      out.push(new Date(cursor));
      cursor.setMinutes(cursor.getMinutes() + 15);
    }
    return out;
  }
  for (let i = 0; i < 96; i++) {
    const d = new Date(anchorDate);
    d.setHours(0, i * 15, 0, 0);
    out.push(d);
  }
  return out;
}

function formatDurationShort(ms) {
  const minutes = Math.max(0, Math.round(ms / 60000));
  if (minutes === 0) return "";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m} min`;
  if (m === 0) return `${h} hr`;
  return `${h} hr ${m} min`;
}

function TimeChipPicker({ value, onChange, anchorDate, durationFrom, ariaLabel }) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState(null); // { top, left, width, openUpward }
  const buttonRef = useRef(null);
  const listRef = useRef(null);
  const hasCenteredRef = useRef(false);

  // Position the portal dropdown beside/below the chip. Flip up if no room.
  function computePosition() {
    if (!buttonRef.current) return;
    const rect = buttonRef.current.getBoundingClientRect();
    const listHeight = 240;
    const spaceBelow = window.innerHeight - rect.bottom;
    const spaceAbove = rect.top;
    const flip = spaceBelow < listHeight + 16 && spaceAbove > spaceBelow;
    setPosition({
      top: flip ? rect.top - 4 : rect.bottom + 4,
      left: rect.left,
      minWidth: rect.width,
      openUpward: flip,
    });
  }

  useEffect(() => {
    if (!open) return;
    computePosition();
    function onResize() { computePosition(); }
    function onScroll() { computePosition(); }
    window.addEventListener("resize", onResize);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      window.removeEventListener("resize", onResize);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [open]);

  // Close when clicking outside the chip or the list.
  useEffect(() => {
    function handleClick(e) {
      const insideChip = buttonRef.current?.contains(e.target);
      const insideList = listRef.current?.contains(e.target);
      if (!insideChip && !insideList) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const options = useMemo(
    () => generateDayTimes(anchorDate, durationFrom),
    [anchorDate, durationFrom],
  );

  // Scroll the selected option into view (centered) when the list opens.
  // The portal only mounts once `position` is measured, so this keys on
  // `position` (not just `open`) and centers exactly once per open —
  // `position` also changes while the user scrolls, and re-centering then
  // would fight their scrolling. Runs after paint via rAF.
  useEffect(() => {
    if (!open) {
      hasCenteredRef.current = false;
      return;
    }
    if (!position || hasCenteredRef.current) return;
    hasCenteredRef.current = true;
    const raf = requestAnimationFrame(() => {
      const list = listRef.current;
      if (!list) return;
      const items = list.querySelectorAll(".gcal-time-item");
      if (items.length === 0) return;
      // Find the selected option, or the nearest one when the value isn't on
      // the 15-min grid. Indexing the options array keeps this correct for
      // the end picker, whose list doesn't start at midnight.
      let targetIndex = options.findIndex(
        (opt) => opt.getHours() === value.getHours() && opt.getMinutes() === value.getMinutes(),
      );
      if (targetIndex === -1) {
        targetIndex = options.findIndex((opt) => opt >= value);
      }
      if (targetIndex === -1) {
        targetIndex = options.length - 1;
      }
      const item = items[Math.min(targetIndex, items.length - 1)];
      list.scrollTop = Math.max(0, item.offsetTop - (list.clientHeight - item.offsetHeight) / 2);
    });
    return () => cancelAnimationFrame(raf);
  }, [open, position, value, options]);

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        className="gcal-chip-button"
        onClick={() => setOpen((v) => !v)}
        aria-label={ariaLabel}
        aria-expanded={open}
      >
        {format12h(value)}
      </button>
      {open && position
        ? createPortal(
            <div
              ref={listRef}
              role="listbox"
              className={position.openUpward ? "gcal-time-list gcal-time-list-up" : "gcal-time-list"}
              style={{
                position: "fixed",
                top: position.openUpward ? "auto" : position.top,
                bottom: position.openUpward ? window.innerHeight - position.top : "auto",
                left: position.left,
                minWidth: position.minWidth,
              }}
            >
              {options.map((opt) => {
                const isActive = opt.getHours() === value.getHours() && opt.getMinutes() === value.getMinutes();
                let durLabel = "";
                if (durationFrom) {
                  // End options are always after the start, so the diff is positive.
                  durLabel = formatDurationShort(opt - durationFrom);
                }
                return (
                  <button
                    key={opt.toISOString()}
                    type="button"
                    className={isActive ? "gcal-time-item active" : "gcal-time-item"}
                    onClick={() => { onChange(opt); setOpen(false); }}
                    role="option"
                    aria-selected={isActive}
                  >
                    <span>{format12h(opt)}</span>
                    {durLabel ? <span className="gcal-time-duration">{durLabel}</span> : null}
                  </button>
                );
              })}
            </div>,
            document.body,
          )
        : null}
    </>
  );
}

function DateChipPicker({ value, onChange }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="gcal-date-chip">
      {open ? (
        <input
          type="date"
          value={dateToISODate(value)}
          autoFocus
          onBlur={() => setOpen(false)}
          onChange={(e) => {
            const [y, m, d] = e.target.value.split("-").map(Number);
            const next = new Date(value);
            next.setFullYear(y, m - 1, d);
            onChange(next);
          }}
        />
      ) : (
        <button type="button" className="gcal-chip-button" onClick={() => setOpen(true)}>
          {formatLongDate(value)}
        </button>
      )}
    </span>
  );
}

export function EventEditorModal({ mode, initialStart, initialEnd, event, onClose, onSaved }) {
  const { user } = useAuth();
  const { selectedClients, selectedClientIds, supportsClientFiltering } = useClientFilter();

  const [title, setTitle] = useState(event?.title || "");
  const [start, setStart] = useState(initialStart);
  const [end, setEnd] = useState(initialEnd);
  const [location, setLocation] = useState(event?.location || "");
  const [meetingLink, setMeetingLink] = useState(event?.meeting_link || "");
  const [description, setDescription] = useState(event?.description || "");
  const [recurrenceType, setRecurrenceType] = useState(event?.recurrence_type || "none");
  const [recurrenceUntil, setRecurrenceUntil] = useState(event?.recurrence_until || "");
  const [addZoomMeeting, setAddZoomMeeting] = useState(false);
  const hasZoomMeeting = Boolean(event?.zoom_meeting_id);
  const [category, setCategory] = useState(event?.category || "");
  const [categories, setCategories] = useState([]);
  const [isLoadingCategories, setIsLoadingCategories] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isExpanded, setIsExpanded] = useState(mode === "edit");
  const titleInputRef = useRef(null);

  // Focus title on open.
  useEffect(() => {
    const id = setTimeout(() => titleInputRef.current?.focus(), 50);
    return () => clearTimeout(id);
  }, []);

  // Close on Escape.
  useEffect(() => {
    function onKey(e) { if (e.key === "Escape") onClose(); }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const isClient = user?.role === "Client";
  const selectedClientId = supportsClientFiltering ? selectedClientIds[0] || "" : user?.id;
  const activeClientId = isClient
    ? user?.id
    : mode === "create"
      ? selectedClientId
      : event?.client?.id || event?.client_id;

  // Load categories for the active client.
  useEffect(() => {
    let alive = true;
    async function load() {
      if (!activeClientId) {
        setCategories([]);
        return;
      }
      setIsLoadingCategories(true);
      try {
        const params = { client_id: activeClientId };
        const results = await fetchAllPages("/categories/", { params });
        if (!alive) return;
        setCategories(results);
        if (mode === "create" && !category && results.length > 0) {
          setCategory(results[0].id);
        }
      } catch (err) {
        if (!alive) return;
        setCategories([]);
      } finally {
        if (alive) setIsLoadingCategories(false);
      }
    }
    load();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeClientId]);

  // Moving the start preserves the event duration (end follows), like any calendar.
  function setStartTime(newStart) {
    const dur = end - start;
    const preserved = dur > 0 ? dur : 60 * 60 * 1000; // fall back to 1h if state was inverted
    setStart(newStart);
    setEnd(new Date(newStart.getTime() + preserved));
  }

  function setEndTime(newEnd) {
    setEnd(newEnd);
  }

  // Keep date of end aligned with start's date (so the date chip controls both).
  function setDate(newDate) {
    const newStart = new Date(start);
    newStart.setFullYear(newDate.getFullYear(), newDate.getMonth(), newDate.getDate());
    const newEnd = new Date(end);
    newEnd.setFullYear(newDate.getFullYear(), newDate.getMonth(), newDate.getDate());
    setStart(newStart);
    setEnd(newEnd);
  }

  const durationMs = end - start;
  const isOvernight = durationMs < 0 || (start.toDateString() === end.toDateString() && durationMs === 0 && end < start);

  async function handleSubmit(e) {
    e.preventDefault();
    setErrorMessage("");

    if (!title.trim()) {
      setErrorMessage("Add a title before saving.");
      titleInputRef.current?.focus();
      return;
    }
    if (!category) {
      setErrorMessage("Pick a category before saving.");
      setIsExpanded(true);
      return;
    }

    setIsSubmitting(true);
    const payload = {
      title: title.trim(),
      event_date: dateToISODate(start),
      start_time: dateToISOTime(start),
      end_time: dateToISOTime(end),
      location,
      meeting_link: meetingLink.trim(),
      description,
      category: Number(category),
      recurrence_type: recurrenceType,
      recurrence_until: recurrenceType === "none" ? null : recurrenceUntil || null,
      client_id: Number(activeClientId),
      create_zoom_meeting: !hasZoomMeeting && addZoomMeeting,
    };

    try {
      const response = event?.id
        ? await apiClient.put(`/events/${event.id}/`, payload)
        : await apiClient.post("/events/", payload);
      if (response?.data?.zoom_status === "failed") {
        window.alert("Event saved, but the Zoom meeting could not be set up. Please try again or contact your coach.");
      }
      onSaved();
    } catch (err) {
      setErrorMessage(getErrorMessage(err, "Unable to save event."));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDelete() {
    if (!event?.id) return;
    if (!window.confirm("Delete this event?")) return;
    setIsSubmitting(true);
    try {
      await apiClient.delete(`/events/${event.id}/`);
      onSaved();
    } catch (err) {
      setErrorMessage(getErrorMessage(err, "Unable to delete event."));
      setIsSubmitting(false);
    }
  }

  return (
    <div className="gcal-modal-backdrop" onClick={onClose}>
      <div className="gcal-modal" onClick={(e) => e.stopPropagation()}>
        <header className="gcal-modal-header">
          <span className="gcal-modal-eyebrow">{mode === "edit" ? "Edit event" : "New event"}</span>
          <button type="button" aria-label="Close" className="gcal-modal-close" onClick={onClose}>×</button>
        </header>

        <form className="gcal-modal-form" onSubmit={handleSubmit}>
          <input
            ref={titleInputRef}
            className="gcal-modal-title"
            placeholder="Add title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />

          <div className="gcal-modal-row">
            <DateChipPicker value={start} onChange={setDate} />
            <TimeChipPicker
              value={start}
              onChange={setStartTime}
              anchorDate={start}
              ariaLabel="Start time"
            />
            <span className="gcal-modal-dash">–</span>
            <TimeChipPicker
              value={end}
              onChange={setEndTime}
              anchorDate={start}
              durationFrom={start}
              ariaLabel="End time"
            />
            <span className="gcal-modal-duration">· {formatDurationShort(durationMs > 0 ? durationMs : durationMs + 24 * 60 * 60 * 1000)}</span>
          </div>

          {isOvernight ? (
            <div className="gcal-modal-warning">Heads up: this event runs overnight (ends the next day).</div>
          ) : null}

          <div className="gcal-modal-row">
            {isLoadingCategories ? (
              <span className="subtle-copy">Loading categories…</span>
            ) : categories.length === 0 ? (
              <span className="subtle-copy">No categories yet — create one in Account Settings → Manage event categories.</span>
            ) : (
              <div className="gcal-select-wrap">
                <select
                  className="gcal-modal-select"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                >
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
                <span className="gcal-select-chevron" aria-hidden>⌄</span>
              </div>
            )}
          </div>

          {isExpanded ? (
            <>
              {event?.meeting_link ? (
                <div className="gcal-modal-row">
                  <a
                    className="gcal-join-link"
                    href={event.meeting_link}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Join meeting →
                  </a>
                </div>
              ) : null}

              <div className="gcal-modal-row">
                <input
                  className="gcal-modal-input"
                  placeholder="Add location"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                />
              </div>

              <div className="gcal-modal-row">
                <label className="gcal-zoom-toggle">
                  <input
                    type="checkbox"
                    checked={hasZoomMeeting || addZoomMeeting}
                    disabled={hasZoomMeeting || isSubmitting}
                    onChange={(e) => setAddZoomMeeting(e.target.checked)}
                  />
                  <span>Add Zoom meeting</span>
                </label>
                {hasZoomMeeting ? (
                  <span className="subtle-copy">Zoom link is managed automatically.</span>
                ) : null}
              </div>

              {hasZoomMeeting ? (
                <div className="gcal-modal-row">
                  <input
                    className="gcal-modal-input"
                    type="url"
                    aria-label="Zoom meeting link"
                    value={meetingLink}
                    readOnly
                  />
                </div>
              ) : addZoomMeeting ? (
                <div className="gcal-modal-row">
                  <span className="subtle-copy">A Zoom link will be added when you save.</span>
                </div>
              ) : (
                <div className="gcal-modal-row">
                  <input
                    className="gcal-modal-input"
                    type="url"
                    placeholder="Add meeting link (Zoom, Meet, etc.)"
                    value={meetingLink}
                    onChange={(e) => setMeetingLink(e.target.value)}
                  />
                </div>
              )}

              <div className="gcal-modal-row">
                <label className="gcal-field-label" htmlFor="event-recurrence-type">Repeats</label>
                <div className="gcal-select-wrap">
                  <select
                    id="event-recurrence-type"
                    className="gcal-modal-select"
                    value={recurrenceType}
                    onChange={(e) => setRecurrenceType(e.target.value)}
                  >
                  <option value="none">Does not repeat</option>
                  <option value="daily">Daily</option>
                  <option value="weekly">Weekly</option>
                  <option value="monthly">Monthly</option>
                </select>
                  <span className="gcal-select-chevron" aria-hidden>⌄</span>
                </div>
                {recurrenceType !== "none" ? (
                  <input
                    type="date"
                    className="gcal-modal-input"
                    style={{ maxWidth: 160 }}
                    value={recurrenceUntil || ""}
                    onChange={(e) => setRecurrenceUntil(e.target.value)}
                    placeholder="Until"
                  />
                ) : null}
              </div>

              <div className="gcal-modal-row gcal-modal-row-top">
                <textarea
                  className="gcal-modal-input"
                  placeholder="Add description"
                  rows={3}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>
            </>
          ) : null}

          {errorMessage ? <p className="form-error">{errorMessage}</p> : null}

          <footer className="gcal-modal-footer">
            {!isExpanded ? (
              <button type="button" className="gcal-modal-link" onClick={() => setIsExpanded(true)}>
                More options
              </button>
            ) : mode === "edit" ? (
              <button type="button" className="gcal-modal-link gcal-modal-delete" onClick={handleDelete} disabled={isSubmitting}>
                Delete
              </button>
            ) : <span />}
            <button type="submit" className="gcal-modal-save" disabled={isSubmitting}>
              {isSubmitting ? "Saving…" : mode === "edit" ? "Save" : "Create"}
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
}
