import { addMonths, formatMonthYear, getMonthGrid, isSameDay, WEEKDAY_LABELS } from "../calendar/calendarUtils";

export function MiniCalendarPopup({ currentDate, onClose, onSelectDate, visibleMonth, onVisibleMonthChange }) {
  const days = getMonthGrid(visibleMonth);

  return (
    <div className="mini-calendar-popup">
      <div className="mini-calendar-header">
        <button onClick={() => onVisibleMonthChange(addMonths(visibleMonth, -1))} type="button">
          {"<"}
        </button>
        <strong>{formatMonthYear(visibleMonth)}</strong>
        <button onClick={() => onVisibleMonthChange(addMonths(visibleMonth, 1))} type="button">
          {">"}
        </button>
        {onClose ? (
          <button aria-label="Close" className="mini-calendar-close" onClick={onClose} type="button">
            ×
          </button>
        ) : null}
      </div>
      <div className="mini-calendar-weekdays">
        {WEEKDAY_LABELS.map((label) => (
          <span key={label}>{label}</span>
        ))}
      </div>
      <div className="mini-calendar-grid">
        {days.map((day) => {
          const isCurrentDay = isSameDay(day, currentDate);
          const isOutsideMonth = day.getMonth() !== visibleMonth.getMonth();

          return (
            <button
              key={day.toISOString()}
              className={isCurrentDay ? "mini-day-button active" : "mini-day-button"}
              data-outside-month={isOutsideMonth}
              onClick={() => onSelectDate(day)}
              type="button"
            >
              {day.getDate()}
            </button>
          );
        })}
      </div>
    </div>
  );
}
