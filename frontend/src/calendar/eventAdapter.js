/**
 * Translates between our API event shape and react-big-calendar's expected shape.
 *
 * API event:
 *   {
 *     id, title, event_date: "2026-05-19", start_time: "09:00:00", end_time: "10:00:00",
 *     location, description, category, category_detail: {id, name, color},
 *     recurrence_type, recurrence_until,
 *     client: {id, label}, client_id
 *   }
 *
 * RBC event:
 *   {
 *     start: Date, end: Date, title: string, resource: <original api object>
 *   }
 *
 * The original API object is preserved on `.resource` so handlers (edit, save)
 * can reach back to the underlying shape without re-fetching.
 */

function buildDate(isoDate, isoTime) {
  // "2026-05-19" + "09:00:00" -> local Date
  const [y, m, d] = isoDate.split("-").map(Number);
  const [hh, mm] = (isoTime || "00:00:00").split(":").map(Number);
  return new Date(y, m - 1, d, hh, mm, 0, 0);
}

export function apiEventToRBC(event) {
  const start = buildDate(event.event_date, event.start_time);
  let end = buildDate(event.event_date, event.end_time);
  // Overnight events (end <= start): roll end into the next day.
  if (end <= start) {
    end = new Date(end.getTime() + 24 * 60 * 60 * 1000);
  }
  return {
    id: event.id,
    title: event.title,
    start,
    end,
    resource: event,
  };
}

export function apiEventsToRBC(events) {
  return events.map(apiEventToRBC);
}

function pad(n) {
  return String(n).padStart(2, "0");
}

export function dateToISODate(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function dateToISOTime(d) {
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/**
 * Build an API payload from a RBC slot/event. Useful for both create
 * (from slot selection) and update (from drag/resize on existing events).
 */
export function rbcRangeToAPIFields({ start, end }) {
  return {
    event_date: dateToISODate(start),
    start_time: dateToISOTime(start),
    end_time: dateToISOTime(end),
  };
}
