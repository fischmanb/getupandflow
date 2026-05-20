import { useCallback, useMemo, useState } from "react";
import { Calendar, Views, dateFnsLocalizer } from "react-big-calendar";
import withDragAndDrop from "react-big-calendar/lib/addons/dragAndDrop";
import { format, parse, startOfWeek, getDay } from "date-fns";
import enUS from "date-fns/locale/en-US";

import { apiClient } from "../api/client";
import { useCalendarControls } from "../calendar/CalendarControlsContext";
import { useClientFilter } from "../filters/ClientFilterContext";
import { apiEventsToRBC, dateToISODate, dateToISOTime } from "../calendar/eventAdapter";
import { getCategoryColorHex } from "../categories/presetColors";
import { EventEditorModal } from "./EventEditorModal";

const locales = { "en-US": enUS };

const localizer = dateFnsLocalizer({
  format,
  parse,
  startOfWeek: () => startOfWeek(new Date(), { weekStartsOn: 0 }),
  getDay,
  locales,
});

const DnDCalendar = withDragAndDrop(Calendar);

const VIEWS = [Views.MONTH, Views.WEEK, Views.DAY, Views.AGENDA];

// In Week/Day views, land the scroll on the start of the workday (7 AM)
// instead of midnight so users don't open onto empty dead hours.
const SCROLL_TO_TIME = new Date(1970, 0, 1, 7, 0, 0);

const VIEW_LABELS = {
  [Views.MONTH]: "Month",
  [Views.WEEK]: "Week",
  [Views.DAY]: "Day",
  [Views.AGENDA]: "Agenda",
};

/**
 * Custom Week/Day column header — Google-Calendar style:
 *   weekday abbreviation (SUN) on top, big day number (17) centered below.
 *   Today gets a blue weekday label + filled blue circle around the number.
 * RBC passes `date` (a Date) and `label` to header components.
 */
function WeekDayHeader({ date }) {
  const weekday = format(date, "EEE").toUpperCase();
  const dayNum = format(date, "d");
  const today = new Date();
  const isToday =
    date.getFullYear() === today.getFullYear() &&
    date.getMonth() === today.getMonth() &&
    date.getDate() === today.getDate();

  return (
    <div className={isToday ? "cal-col-header is-today" : "cal-col-header"}>
      <span className="cal-col-weekday">{weekday}</span>
      <span className="cal-col-daynum">{dayNum}</span>
    </div>
  );
}

/**
 * Custom toolbar replacing RBC's default. Three clean zones:
 *   left:   Today + prev/next arrows
 *   center: the current period label
 *   right:  view switcher (Month/Week/Day/Agenda)
 * RBC injects label/onNavigate/onView/view props.
 */
function CalendarToolbar({ label, onNavigate, onView, view }) {
  return (
    <div className="cal-toolbar">
      <div className="cal-toolbar-nav">
        <button type="button" className="cal-toolbar-today" onClick={() => onNavigate("TODAY")}>
          Today
        </button>
        <div className="cal-toolbar-arrows">
          <button type="button" aria-label="Previous" onClick={() => onNavigate("PREV")}>
            ‹
          </button>
          <button type="button" aria-label="Next" onClick={() => onNavigate("NEXT")}>
            ›
          </button>
        </div>
      </div>

      <span className="cal-toolbar-label">{label}</span>

      <div className="cal-toolbar-views">
        {VIEWS.map((v) => (
          <button
            key={v}
            type="button"
            className={v === view ? "cal-toolbar-view active" : "cal-toolbar-view"}
            onClick={() => onView(v)}
          >
            {VIEW_LABELS[v]}
          </button>
        ))}
      </div>
    </div>
  );
}

function getEventPromptMessage(count) {
  return count === 0
    ? "Select a client before creating an event."
    : "Select exactly one client before creating an event.";
}

export function BigCalendarPanel({ className }) {
  const { colorMap, eventError, events, isLoadingEvents, refreshEvents, selectedClientIds, supportsClientFiltering } =
    useClientFilter();
  const { currentDate, setCurrentDate, view, setView } = useCalendarControls();

  const [editor, setEditor] = useState(null); // { mode, initialStart, initialEnd, event }
  const [createPrompt, setCreatePrompt] = useState("");

  const canCreate = !supportsClientFiltering || selectedClientIds.length === 1;

  const rbcEvents = useMemo(() => apiEventsToRBC(events), [events]);

  // Color events by their category's color, falling back to client color.
  const eventPropGetter = useCallback(
    (event) => {
      const api = event.resource;
      const categoryColor = api?.category_detail?.color;
      const clientColor = api?.client?.id ? colorMap[api.client.id] : undefined;
      const color = categoryColor ? getCategoryColorHex(categoryColor) : clientColor || "#2563eb";
      return {
        style: {
          backgroundColor: color,
          borderRadius: "6px",
          color: "#fff",
          border: "none",
        },
      };
    },
    [colorMap],
  );

  function handleSelectSlot({ start, end, action }) {
    if (!canCreate) {
      setCreatePrompt(getEventPromptMessage(selectedClientIds.length));
      return;
    }
    // RBC sends 'click' for empty-cell click (start === end); we treat as a
    // 1-hour default. 'select' covers drag-to-create.
    let s = new Date(start);
    let e = new Date(end);
    if (action === "click" || +s === +e) {
      s.setHours(9, 0, 0, 0);
      e = new Date(s.getTime() + 60 * 60 * 1000);
    }
    setCreatePrompt("");
    setEditor({ mode: "create", initialStart: s, initialEnd: e, event: null });
  }

  function handleSelectEvent(rbcEvent) {
    setEditor({
      mode: "edit",
      initialStart: rbcEvent.start,
      initialEnd: rbcEvent.end,
      event: rbcEvent.resource,
    });
  }

  async function handleEventDrop({ event, start, end }) {
    // Drag-to-move. Optimistically save with new times.
    const api = event.resource;
    if (!api) return;
    try {
      await apiClient.patch(`/events/${api.id}/`, {
        event_date: dateToISODate(start),
        start_time: dateToISOTime(start),
        end_time: dateToISOTime(end),
      });
      await refreshEvents();
    } catch (err) {
      console.error("Failed to move event:", err);
      await refreshEvents(); // refresh to revert visual
    }
  }

  async function handleEventResize({ event, start, end }) {
    const api = event.resource;
    if (!api) return;
    try {
      await apiClient.patch(`/events/${api.id}/`, {
        event_date: dateToISODate(start),
        start_time: dateToISOTime(start),
        end_time: dateToISOTime(end),
      });
      await refreshEvents();
    } catch (err) {
      console.error("Failed to resize event:", err);
      await refreshEvents();
    }
  }

  async function handleSaved() {
    setEditor(null);
    await refreshEvents();
  }

  return (
    <article className={className}>
      {createPrompt ? <p className="form-error">{createPrompt}</p> : null}
      {eventError ? <p className="form-error">{eventError}</p> : null}
      {isLoadingEvents ? <p className="subtle-copy">Loading calendar events…</p> : null}

      <div className="rbc-shell" style={{ height: "75vh", minHeight: 600 }}>
        <DnDCalendar
          localizer={localizer}
          events={rbcEvents}
          views={VIEWS}
          view={view}
          onView={setView}
          date={currentDate}
          onNavigate={setCurrentDate}
          startAccessor="start"
          endAccessor="end"
          selectable
          onSelectSlot={handleSelectSlot}
          onSelectEvent={handleSelectEvent}
          onEventDrop={handleEventDrop}
          onEventResize={handleEventResize}
          resizable
          eventPropGetter={eventPropGetter}
          components={{
            toolbar: CalendarToolbar,
            week: { header: WeekDayHeader },
            day: { header: WeekDayHeader },
          }}
          step={30}
          timeslots={2}
          scrollToTime={SCROLL_TO_TIME}
          dayLayoutAlgorithm="no-overlap"
          popup
        />
      </div>

      {editor ? (
        <EventEditorModal
          mode={editor.mode}
          initialStart={editor.initialStart}
          initialEnd={editor.initialEnd}
          event={editor.event}
          onClose={() => setEditor(null)}
          onSaved={handleSaved}
        />
      ) : null}
    </article>
  );
}
