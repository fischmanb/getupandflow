import { useEffect, useMemo, useRef, useState } from "react";

import { apiClient } from "../api/client";
import { fetchAllPages, getErrorMessage } from "../api/utils";
import { useAuth } from "../auth/AuthContext";
import { useClientFilter } from "../filters/ClientFilterContext";
import { useOutsideClick } from "../hooks/useOutsideClick";
import { TimeWheelPicker } from "./TimeWheelPicker";

/**
 * QuickEventPopover
 * Two-stage event create/edit form.
 *
 * Stage 1 ("quick"): Title input (autofocused) + inline editable date/time + Category + Save / More options.
 * Stage 2 ("expanded"): Adds Location, Recurrence, Description below.
 *
 * Editing an existing event opens directly in expanded mode so users see all the data.
 *
 * Anchored absolutely by the parent via `style` (same convention as DayAgendaPanel).
 */

function pad(n) {
  return String(n).padStart(2, "0");
}

function formatDateLong(isoDate) {
  if (!isoDate) return "";
  const [y, m, d] = isoDate.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  return date.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
}

function formatTime12h(hhmm) {
  if (!hhmm) return "";
  const [hStr, mStr] = hhmm.split(":");
  const h = Number(hStr);
  const m = Number(mStr);
  const period = h >= 12 ? "PM" : "AM";
  const displayH = h % 12 === 0 ? 12 : h % 12;
  return `${displayH}:${pad(m)} ${period}`;
}

function addHours(hhmm, hours) {
  const [h, m] = hhmm.split(":").map(Number);
  const totalMin = h * 60 + m + hours * 60;
  const wrapped = ((totalMin % (24 * 60)) + 24 * 60) % (24 * 60);
  return `${pad(Math.floor(wrapped / 60))}:${pad(wrapped % 60)}`;
}

function minutesBetween(startHHMM, endHHMM) {
  const [sh, sm] = startHHMM.split(":").map(Number);
  const [eh, em] = endHHMM.split(":").map(Number);
  let diff = eh * 60 + em - (sh * 60 + sm);
  if (diff < 0) diff += 24 * 60; // overnight: treat end as next day
  return diff;
}

function isOvernight(startHHMM, endHHMM) {
  return endHHMM <= startHHMM;
}

function formatDuration(minutes) {
  if (minutes <= 0) return "";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m} min`;
  if (m === 0) return `${h} hr`;
  return `${h} hr ${m} min`;
}

function getDefaultTimes() {
  return { start_time: "09:00", end_time: "10:00" };
}

function getInitialState(event, defaultClientId, initialDate = "") {
  const defaults = getDefaultTimes();
  return {
    title: event?.title || "",
    event_date: event?.event_date || initialDate || "",
    start_time: event?.start_time?.slice(0, 5) || defaults.start_time,
    end_time: event?.end_time?.slice(0, 5) || defaults.end_time,
    location: event?.location || "",
    description: event?.description || "",
    category: event?.category || "",
    recurrence_type: event?.recurrence_type || "none",
    recurrence_until: event?.recurrence_until || "",
    client_id: event?.client?.id || defaultClientId || "",
  };
}

export function QuickEventPopover({ event, initialDate, onCancel, onSaved, style }) {
  const { user } = useAuth();
  const { selectedClients, selectedClientIds, supportsClientFiltering } = useClientFilter();

  const [categories, setCategories] = useState([]);
  const [categoryError, setCategoryError] = useState("");
  const [isLoadingCategories, setIsLoadingCategories] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  // Existing events open expanded so users see everything they're editing.
  const [isExpanded, setIsExpanded] = useState(Boolean(event));
  const [isEditingTime, setIsEditingTime] = useState(false);
  const [isEditingDate, setIsEditingDate] = useState(false);

  const [formState, setFormState] = useState(() =>
    getInitialState(event, selectedClientIds[0] || user?.id, initialDate),
  );

  const initialFormState = useMemo(
    () => getInitialState(event, selectedClientIds[0] || user?.id, initialDate),
    [event, initialDate, selectedClientIds, user?.id],
  );
  const isDirty = useMemo(
    () => JSON.stringify(formState) !== JSON.stringify(initialFormState),
    [formState, initialFormState],
  );

  const cardRef = useRef(null);
  const titleInputRef = useRef(null);

  function attemptCancel() {
    if (isDirty && !window.confirm("Discard your changes?")) return;
    onCancel();
  }
  useOutsideClick(cardRef, attemptCancel, true);

  // Autofocus the title input on open. The brief timeout sidesteps a focus race
  // when the popover mounts as a sibling of an animated parent.
  useEffect(() => {
    const id = setTimeout(() => titleInputRef.current?.focus(), 50);
    return () => clearTimeout(id);
  }, []);

  // Reload form state when underlying record changes (e.g. switching from one event edit to another).
  useEffect(() => {
    setFormState(getInitialState(event, selectedClientIds[0] || user?.id, initialDate));
  }, [event, initialDate, selectedClientIds, user?.id]);

  const isClient = user?.role === "Client";
  const isCreateMode = !event;
  const eligibleClients = supportsClientFiltering
    ? selectedClients
    : [{ id: user?.id, label: user?.first_name || user?.username }];
  const selectedClientId = supportsClientFiltering ? selectedClientIds[0] || "" : user?.id;
  const activeClientId = isClient ? user?.id : isCreateMode ? selectedClientId : formState.client_id;

  // Load category options whenever the active client changes.
  useEffect(() => {
    let isMounted = true;
    async function load() {
      setIsLoadingCategories(true);
      setCategoryError("");
      try {
        const params = activeClientId ? { client_id: activeClientId } : undefined;
        const results = await fetchAllPages("/categories/", { params });
        if (!isMounted) return;
        setCategories(results);
        // Default category to the first one if creating and none picked yet.
        if (isCreateMode && !formState.category && results.length > 0) {
          setFormState((current) => ({ ...current, category: results[0].id }));
        }
        // If the currently-set category is no longer valid (client switch), clear it.
        if (formState.category && !results.some((c) => c.id === Number(formState.category))) {
          setFormState((current) => ({ ...current, category: "" }));
        }
      } catch (err) {
        if (isMounted) {
          setCategories([]);
          setCategoryError(getErrorMessage(err, "Couldn't load categories."));
        }
      } finally {
        if (isMounted) setIsLoadingCategories(false);
      }
    }
    if (activeClientId) load();
    else setCategories([]);
    return () => {
      isMounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeClientId]);

  // When user changes start, shift end forward by the same delta so duration is preserved.
  function setStartTime(newStart) {
    setFormState((current) => {
      const oldDuration = minutesBetween(current.start_time, current.end_time);
      const [h, m] = newStart.split(":").map(Number);
      const startMin = h * 60 + m;
      const endMin = (startMin + oldDuration) % (24 * 60);
      const newEnd = `${pad(Math.floor(endMin / 60))}:${pad(endMin % 60)}`;
      return { ...current, start_time: newStart, end_time: newEnd };
    });
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!formState.title.trim()) {
      setErrorMessage("Add a title before saving.");
      titleInputRef.current?.focus();
      return;
    }
    if (!formState.category) {
      setErrorMessage("Pick a category before saving.");
      setIsExpanded(true);
      return;
    }
    if (!formState.event_date) {
      setErrorMessage("Pick a date before saving.");
      return;
    }

    setErrorMessage("");
    setIsSubmitting(true);

    const payload = {
      ...formState,
      client_id: isClient ? user.id : Number(isCreateMode ? selectedClientId : formState.client_id),
      category: Number(formState.category),
      start_time: `${formState.start_time}:00`,
      end_time: `${formState.end_time}:00`,
      recurrence_until: formState.recurrence_type === "none" ? null : formState.recurrence_until,
    };

    try {
      if (event) await apiClient.put(`/events/${event.id}/`, payload);
      else await apiClient.post("/events/", payload);
      onSaved();
    } catch (err) {
      setErrorMessage(getErrorMessage(err, "Unable to save event."));
    } finally {
      setIsSubmitting(false);
    }
  }

  // Client picker only relevant in create mode when the coach has multiple clients selected.
  const showClientPicker =
    !isClient && isCreateMode && supportsClientFiltering && eligibleClients.length > 1;

  return (
    <section className="quick-event-popover" ref={cardRef} style={style}>
      <form className="quick-event-form" onSubmit={handleSubmit}>
        <header className="quick-event-header">
          <h4>{event ? "Edit event" : "New event"}</h4>
          <button aria-label="Close" className="entity-form-dismiss" onClick={attemptCancel} type="button">
            ×
          </button>
        </header>

        <input
          aria-label="Title"
          className="quick-event-title-input"
          placeholder="Add title"
          ref={titleInputRef}
          value={formState.title}
          onChange={(e) => setFormState((current) => ({ ...current, title: e.target.value }))}
        />

        <div className="quick-event-meta">
          {isEditingDate ? (
            <input
              type="date"
              className="quick-event-meta-input"
              value={formState.event_date}
              autoFocus
              onBlur={() => setIsEditingDate(false)}
              onChange={(e) => setFormState((current) => ({ ...current, event_date: e.target.value }))}
            />
          ) : (
            <button
              type="button"
              className="quick-event-meta-chip"
              onClick={() => setIsEditingDate(true)}
              title="Click to change date"
            >
              {formatDateLong(formState.event_date) || "Pick a date"}
            </button>
          )}

          {isEditingTime ? (
            <div className="quick-event-time-picker">
              <div className="quick-event-time-row">
                <div className="quick-event-time-col">
                  <span className="quick-event-time-col-label">Start</span>
                  <TimeWheelPicker
                    value={formState.start_time}
                    onChange={setStartTime}
                    label="Start time"
                  />
                </div>
                <div className="quick-event-time-col">
                  <span className="quick-event-time-col-label">End</span>
                  <TimeWheelPicker
                    value={formState.end_time}
                    onChange={(v) => setFormState((current) => ({ ...current, end_time: v }))}
                    label="End time"
                  />
                </div>
              </div>
              <div className="quick-event-time-row" style={{ alignItems: "center", justifyContent: "space-between" }}>
                <span className="quick-event-duration-label">
                  Duration: {formatDuration(minutesBetween(formState.start_time, formState.end_time))}
                </span>
                <button
                  type="button"
                  className="quick-event-time-done"
                  onClick={() => setIsEditingTime(false)}
                >
                  Done
                </button>
              </div>
              {isOvernight(formState.start_time, formState.end_time) ? (
                <span className="quick-event-overnight-warning">
                  Heads up: this event runs overnight (ends the next day).
                </span>
              ) : null}
            </div>
          ) : (
            <button
              type="button"
              className="quick-event-meta-chip"
              onClick={() => setIsEditingTime(true)}
              title="Click to change time"
            >
              {formatTime12h(formState.start_time)} – {formatTime12h(formState.end_time)}
              <span className="quick-event-duration-label" style={{ marginLeft: 8 }}>
                · {formatDuration(minutesBetween(formState.start_time, formState.end_time))}
              </span>
            </button>
          )}
        </div>

        <label className="quick-event-field">
          <span className="quick-event-field-label">Category</span>
          {isLoadingCategories ? (
            <span className="subtle-copy">Loading categories…</span>
          ) : (
            <select
              required
              value={formState.category}
              onChange={(e) => setFormState((current) => ({ ...current, category: e.target.value }))}
            >
              <option value="">Select category</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          )}
          {categoryError ? <span className="form-error">{categoryError}</span> : null}
        </label>

        {showClientPicker ? (
          <label className="quick-event-field">
            <span className="quick-event-field-label">Client</span>
            <select
              value={formState.client_id}
              onChange={(e) => setFormState((current) => ({ ...current, client_id: e.target.value }))}
            >
              {eligibleClients.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        {isExpanded ? (
          <div className="quick-event-expanded">
            <label className="quick-event-field">
              <span className="quick-event-field-label">Location</span>
              <input
                value={formState.location}
                onChange={(e) => setFormState((current) => ({ ...current, location: e.target.value }))}
                placeholder="Add location"
              />
            </label>

            <label className="quick-event-field">
              <span className="quick-event-field-label">Repeats</span>
              <select
                value={formState.recurrence_type}
                onChange={(e) =>
                  setFormState((current) => ({ ...current, recurrence_type: e.target.value }))
                }
              >
                <option value="none">Does not repeat</option>
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="monthly">Monthly</option>
              </select>
            </label>

            {formState.recurrence_type !== "none" ? (
              <label className="quick-event-field">
                <span className="quick-event-field-label">Repeats until</span>
                <input
                  type="date"
                  value={formState.recurrence_until || ""}
                  onChange={(e) =>
                    setFormState((current) => ({ ...current, recurrence_until: e.target.value }))
                  }
                />
              </label>
            ) : null}

            <label className="quick-event-field">
              <span className="quick-event-field-label">Description</span>
              <textarea
                value={formState.description}
                onChange={(e) => setFormState((current) => ({ ...current, description: e.target.value }))}
                placeholder="Add notes"
                rows={3}
              />
            </label>
          </div>
        ) : null}

        {errorMessage ? <p className="form-error">{errorMessage}</p> : null}

        <footer className="quick-event-footer">
          {!isExpanded ? (
            <button
              type="button"
              className="quick-event-more"
              onClick={() => setIsExpanded(true)}
            >
              More options
            </button>
          ) : (
            <span />
          )}
          <button className="primary-button" disabled={isSubmitting} type="submit">
            {isSubmitting ? "Saving…" : event ? "Save" : "Create event"}
          </button>
        </footer>
      </form>
    </section>
  );
}
