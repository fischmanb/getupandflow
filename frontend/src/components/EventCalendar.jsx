import { useEffect, useMemo, useRef, useState } from "react";

import {
  addDays,
  addMonths,
  endOfMonth,
  endOfWeek,
  formatDayHeader,
  formatLongDate,
  getEventsForDate,
  getEventsForRange,
  getMonthGrid,
  getViewTitle,
  getWeekDays,
  isSameDay,
  parseEventDate,
  startOfMonth,
  startOfWeek,
} from "../calendar/calendarUtils";
import { useCalendarControls } from "../calendar/CalendarControlsContext";
import { CalendarToolbar } from "./CalendarToolbar";
import { MiniCalendarPopup } from "./MiniCalendarPopup";

function formatTimeRange(event) {
  return `${event.start_time.slice(0, 5)} - ${event.end_time.slice(0, 5)}`;
}

function EventPill({ color, event, onSelect }) {
  return (
    <button className="calendar-event-pill" onClick={() => onSelect(event)} style={{ "--event-color": color }} type="button">
      <strong>{event.title}</strong>
      <span>{formatTimeRange(event)}</span>
      <small>{event.client_name}</small>
    </button>
  );
}

function formatDateForInput(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatMonthCellLabel(day, currentDate) {
  if (day.getDate() === 1 || day.getMonth() !== currentDate.getMonth()) {
    return day.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  return String(day.getDate());
}

function DayView({ colorMap, currentDate, events, onSelectEvent }) {
  const dayEvents = getEventsForDate(events, currentDate);

  return (
    <div className="calendar-body day-view">
      <div className="calendar-column">
        <header className="calendar-column-header">
          <strong>{formatLongDate(currentDate)}</strong>
          <span>{dayEvents.length} events</span>
        </header>
        <div className="calendar-column-content">
          {dayEvents.length === 0 ? <p className="subtle-copy">No events scheduled for this day.</p> : null}
          {dayEvents.map((event) => (
            <EventPill
              key={event.id}
              color={colorMap[event.client?.id] || "#0f766e"}
              event={event}
              onSelect={onSelectEvent}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function WeekView({ colorMap, currentDate, events, onSelectEvent }) {
  const weekDays = getWeekDays(currentDate);

  return (
    <div className="calendar-body week-view">
      {weekDays.map((day) => {
        const dayEvents = getEventsForDate(events, day);

        return (
          <section key={day.toISOString()} className="calendar-column">
            <header className="calendar-column-header">
              <strong>{formatDayHeader(day)}</strong>
              <span>{dayEvents.length} events</span>
            </header>
            <div className="calendar-column-content">
              {dayEvents.map((event) => (
                <EventPill
                  key={event.id}
                  color={colorMap[event.client?.id] || "#0f766e"}
                  event={event}
                  onSelect={onSelectEvent}
                />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function DayAgendaPanel({ colorMap, date, events, onClose, onCreateForDate, onSelectEvent, style }) {
  const dayEvents = getEventsForDate(events, date);

  return (
    <section className="day-agenda-panel" style={style}>
      <div className="day-agenda-header">
        <h4>{formatLongDate(date)}</h4>
        <button aria-label="Close" className="entity-form-dismiss" onClick={onClose} type="button">
          ×
        </button>
      </div>
      {dayEvents.length > 0 ? (
        <div className="day-agenda-list">
          {dayEvents.map((event) => (
            <EventPill
              key={`${event.id}-${event.occurrence_date || event.event_date}`}
              color={colorMap[event.client?.id] || "#0f766e"}
              event={event}
              onSelect={onSelectEvent}
            />
          ))}
        </div>
      ) : null}
      <div className="day-agenda-actions">
        <button className="task-create-button" onClick={() => onCreateForDate(formatDateForInput(date))} type="button">
          +
        </button>
      </div>
    </section>
  );
}

function MonthView({ colorMap, currentDate, events, onCreateForDate, onSelectDate, onSelectEvent, selectedDate }) {
  const monthDays = getMonthGrid(currentDate);

  return (
    <div className="calendar-body month-view">
      <div className="month-weekday-row">
        {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((label) => (
          <div key={label} className="month-weekday-cell">
            {label}
          </div>
        ))}
      </div>
      <div className="month-grid">
        {monthDays.map((day) => {
          const dayEvents = getEventsForDate(events, day).slice(0, 3);
          const isCurrentMonth = day.getMonth() === currentDate.getMonth();
          const isToday = isSameDay(day, new Date());

          return (
            <article
              key={day.toISOString()}
              className="month-day-cell"
              data-current-month={isCurrentMonth}
              data-selected={selectedDate ? isSameDay(day, selectedDate) : false}
              data-today={isToday}
              onClick={(event) => onSelectDate(day, event.currentTarget)}
            >
              <header className="month-day-header">
                <span className="month-day-number">{formatMonthCellLabel(day, currentDate)}</span>
              </header>
              <div className="month-day-events">
                {dayEvents.map((event) => (
                  <button
                    key={event.id}
                    className="month-event-chip"
                    onClick={(clickEvent) => {
                      clickEvent.stopPropagation();
                      onSelectEvent(event);
                    }}
                    style={{ "--event-color": colorMap[event.client?.id] || "#0f766e" }}
                    type="button"
                  >
                    <span>{event.title}</span>
                  </button>
                ))}
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}

export function EventCalendar({ colorMap, events, onCreateForDate, onSelectEvent }) {
  const { currentDate, setCurrentDate, view } = useCalendarControls();
  const [isMiniCalendarOpen, setIsMiniCalendarOpen] = useState(false);
  const [selectedDate, setSelectedDate] = useState(null);
  const [agendaPosition, setAgendaPosition] = useState(null);
  const [visibleMonth, setVisibleMonth] = useState(startOfMonth(new Date()));
  const monthViewRef = useRef(null);

  useEffect(() => {
    setVisibleMonth(startOfMonth(currentDate));
  }, [currentDate]);

  const currentTitle = useMemo(() => getViewTitle(view, currentDate), [currentDate, view]);

  function handleNavigate(direction) {
    setCurrentDate((current) => {
      let nextDate = current;
      if (view === "day") {
        nextDate = addDays(current, direction);
      } else if (view === "week") {
        nextDate = addDays(current, direction * 7);
      } else {
        nextDate = addMonths(current, direction);
      }
      setVisibleMonth(startOfMonth(nextDate));
      return nextDate;
    });
  }

  function handleSelectDate(date, anchorElement = null) {
    setCurrentDate(date);
    setSelectedDate(date);
    setVisibleMonth(startOfMonth(date));
    setIsMiniCalendarOpen(false);

    if (anchorElement && monthViewRef.current) {
      const containerRect = monthViewRef.current.getBoundingClientRect();
      const anchorRect = anchorElement.getBoundingClientRect();
      const estimatedPanelWidth = Math.min(440, Math.max(280, containerRect.width - 24));
      const estimatedPanelHeight = 260;
      const preferredLeft = anchorRect.left - containerRect.left + (anchorRect.width / 2) - (estimatedPanelWidth / 2);
      const preferredTop = anchorRect.top - containerRect.top + anchorRect.height + 10;
      const maxLeft = Math.max(12, containerRect.width - estimatedPanelWidth - 12);
      const left = Math.min(Math.max(12, preferredLeft), maxLeft);
      const maxTop = Math.max(12, containerRect.height - estimatedPanelHeight - 12);
      const top =
        preferredTop + estimatedPanelHeight <= containerRect.height
          ? preferredTop
          : Math.min(Math.max(12, anchorRect.top - containerRect.top - estimatedPanelHeight - 10), maxTop);

      setAgendaPosition({ left, top });
    } else {
      setAgendaPosition(null);
    }
  }

  return (
    <div className="calendar-shell">
      <div className="calendar-toolbar-wrap">
        <CalendarToolbar
          currentTitle={currentTitle}
          isMiniCalendarOpen={isMiniCalendarOpen}
          onNavigate={handleNavigate}
          onToggleMiniCalendar={() => setIsMiniCalendarOpen((current) => !current)}
        />
        {isMiniCalendarOpen ? (
          <MiniCalendarPopup
            currentDate={currentDate}
            onSelectDate={handleSelectDate}
            onVisibleMonthChange={setVisibleMonth}
            visibleMonth={visibleMonth}
          />
        ) : null}
      </div>

      {view === "day" ? <DayView colorMap={colorMap} currentDate={currentDate} events={events} onSelectEvent={onSelectEvent} /> : null}
      {view === "week" ? <WeekView colorMap={colorMap} currentDate={currentDate} events={events} onSelectEvent={onSelectEvent} /> : null}
      {view === "month" ? (
        <div className="month-view-shell">
          {selectedDate ? (
            <DayAgendaPanel
              colorMap={colorMap}
              date={selectedDate}
              events={events}
              onClose={() => setSelectedDate(null)}
              onCreateForDate={onCreateForDate}
              onSelectEvent={onSelectEvent}
              style={agendaPosition ? { left: `${agendaPosition.left}px`, top: `${agendaPosition.top}px` } : undefined}
            />
          ) : null}
          <div ref={monthViewRef}>
            <MonthView
              colorMap={colorMap}
              currentDate={currentDate}
              events={events}
              onCreateForDate={onCreateForDate}
              onSelectDate={handleSelectDate}
              onSelectEvent={onSelectEvent}
              selectedDate={selectedDate}
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}
