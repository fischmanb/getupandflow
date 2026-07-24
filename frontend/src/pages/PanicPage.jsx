import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "../api/client";
import { useAuth } from "../auth/AuthContext";

const DURATIONS = [15, 30];

// All display goes through the timezone the API names (the client's stored
// onboarding timezone) — never the browser's guess.
function dayKeyIn(timeZone, date = new Date()) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function formatSlotTime(iso, timeZone) {
  return new Intl.DateTimeFormat("en-US", { timeZone, hour: "numeric", minute: "2-digit" })
    .format(new Date(iso))
    .toLowerCase();
}

function formatWhen(iso, timeZone) {
  const date = new Date(iso);
  const day = new Intl.DateTimeFormat("en-US", {
    timeZone,
    weekday: "long",
    month: "long",
    day: "numeric",
  }).format(date);
  return `${day} at ${formatSlotTime(iso, timeZone)}`;
}

function dayTabLabel(dateKey, timeZone) {
  if (dateKey === dayKeyIn(timeZone)) return "Today";
  if (dateKey === dayKeyIn(timeZone, new Date(Date.now() + 24 * 60 * 60 * 1000))) return "Tomorrow";
  const [year, month, day] = dateKey.split("-").map(Number);
  return new Intl.DateTimeFormat("en-US", { weekday: "long", timeZone: "UTC" }).format(
    new Date(Date.UTC(year, month - 1, day)),
  );
}

function MatchingNotice() {
  return (
    <main className="home-room panic-room">
      <h2 className="home-greeting">Stuck is normal.</h2>
      <p className="panic-lede">
        Your coach is almost here — we&apos;re matching you now, and the Panic Button unlocks the
        moment they&apos;re in place.
      </p>
      <Link className="task-create-button" to="/app">
        Back home
      </Link>
    </main>
  );
}

function TodaysSessions({ sessions, timeZone, onCancel, cancellingId }) {
  if (!sessions.length) return null;

  return (
    <section className="panic-booked-section">
      <p className="panel-label">Booked</p>
      <ul className="panic-booked-list">
        {sessions.map((session) => (
          <li key={session.id} className="panic-booked-row">
            <span>
              {formatWhen(session.start_at, timeZone)} · {session.duration_minutes} min
            </span>
            {session.can_cancel ? (
              <button
                className="panic-cancel-button"
                disabled={cancellingId === session.id}
                type="button"
                onClick={() => onCancel(session.id)}
              >
                {cancellingId === session.id ? "Cancelling..." : "Cancel"}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function PanicPage() {
  const { user } = useAuth();
  const hasCoach = Boolean(user?.my_coach);
  const coachFirstName = (user?.my_coach?.name || "your coach").split(" ")[0];

  const [duration, setDuration] = useState(15);
  const [availability, setAvailability] = useState(null);
  const [isLoadingSlots, setIsLoadingSlots] = useState(false);
  const [selectedDay, setSelectedDay] = useState(null);
  const [selectedStart, setSelectedStart] = useState(null);
  const [note, setNote] = useState("");
  const [booking, setBooking] = useState({ status: "idle" });
  const [cancellingId, setCancellingId] = useState(null);
  const [mySessions, setMySessions] = useState(null);
  const [loadError, setLoadError] = useState("");

  const loadAvailability = useCallback(
    async (nextDuration = duration) => {
      setIsLoadingSlots(true);
      setLoadError("");
      try {
        const response = await apiClient.get("/panic-availability/", {
          params: { duration: nextDuration },
        });
        setAvailability(response.data);
        setSelectedDay((current) =>
          response.data.days.some((day) => day.date === current)
            ? current
            : response.data.days[0]?.date || null,
        );
        setSelectedStart(null);
      } catch (error) {
        setAvailability(null);
        setLoadError(
          error.response?.data?.detail || "We couldn't load your coach's open times — try again in a moment.",
        );
      } finally {
        setIsLoadingSlots(false);
      }
    },
    [duration],
  );

  const loadSessions = useCallback(async () => {
    try {
      const response = await apiClient.get("/panic-sessions/");
      setMySessions(response.data);
    } catch {
      setMySessions(null);
    }
  }, []);

  useEffect(() => {
    if (!hasCoach) return;
    loadAvailability();
    loadSessions();
  }, [hasCoach, loadAvailability, loadSessions]);

  if (!hasCoach) {
    return <MatchingNotice />;
  }

  const book = async (startIso) => {
    setBooking({ status: "booking" });
    try {
      const payload = { duration, start_time: startIso };
      if (note.trim()) payload.note = note.trim();
      const response = await apiClient.post("/panic-sessions/", payload);
      setBooking({ status: "success", session: response.data });
      setNote("");
      setSelectedStart(null);
      await Promise.all([loadAvailability(), loadSessions()]);
    } catch (error) {
      const data = error.response?.data || {};
      const message =
        data.detail ||
        data.start_time ||
        data.duration ||
        data.note ||
        "We couldn't book that — try again in a moment.";
      setBooking({
        status: "error",
        message: Array.isArray(message) ? message[0] : message,
        suggestions: data.suggestions || [],
      });
      if (error.response?.status === 409) {
        await loadAvailability();
      }
    }
  };

  const cancelSession = async (id) => {
    setCancellingId(id);
    try {
      await apiClient.delete(`/panic-sessions/${id}/`);
      setBooking({ status: "idle" });
      await Promise.all([loadAvailability(), loadSessions()]);
    } catch {
      setBooking({ status: "error", message: "We couldn't cancel that — try again in a moment." });
    } finally {
      setCancellingId(null);
    }
  };

  // Changing the duration refetches through the effect (loadAvailability's
  // identity tracks `duration`).
  const chooseDuration = (value) => {
    if (value === duration || booking.status === "booking") return;
    setDuration(value);
    setBooking({ status: "idle" });
  };

  const timeZone = availability?.timezone || mySessions?.timezone;
  const remaining = mySessions?.remaining_minutes_today ?? availability?.remaining_minutes_today;
  const days = availability?.days || [];
  const activeDay = days.find((day) => day.date === selectedDay) || days[0] || null;
  const confirmed = booking.status === "success" ? booking.session : null;

  return (
    <main className="home-room panic-room">
      <h2 className="home-greeting">Stuck is normal. Grab your coach.</h2>
      <p className="panic-lede">
        Book {DURATIONS.join(" or ")} minutes with {coachFirstName} to get moving again. No shame in
        it — that&apos;s what this time is for.
      </p>

      {typeof remaining === "number" ? (
        <p className="panic-remaining">
          {remaining > 0
            ? `You have ${remaining} panic minutes left today.`
            : "You've used today's panic minutes — they reset at midnight."}
        </p>
      ) : null}

      {mySessions?.sessions?.length ? (
        <TodaysSessions
          cancellingId={cancellingId}
          sessions={mySessions.sessions}
          timeZone={mySessions.timezone}
          onCancel={cancelSession}
        />
      ) : null}

      {confirmed ? (
        <div className="panic-confirmation" role="status">
          <p>
            You&apos;re booked — {formatWhen(confirmed.start_at, confirmed.timezone || timeZone)},{" "}
            {confirmed.duration_minutes} minutes with {coachFirstName}.
          </p>
          <p>
            <Link to="/app/calendar">See it on your calendar</Link>
          </p>
        </div>
      ) : null}

      <section className="panic-booking-section">
        <p className="panel-label">How long do you need?</p>
        <div aria-label="Session length" className="panic-duration-toggle" role="group">
          {DURATIONS.map((value) => (
            <button
              key={value}
              aria-pressed={duration === value}
              className={duration === value ? "panic-duration-button is-selected" : "panic-duration-button"}
              type="button"
              onClick={() => chooseDuration(value)}
            >
              {value} minutes
            </button>
          ))}
        </div>

        {loadError ? <p className="form-error">{loadError}</p> : null}
        {isLoadingSlots ? <p className="subtle-copy">Finding open times…</p> : null}

        {!isLoadingSlots && availability ? (
          days.length ? (
            <>
              <div aria-label="Choose a day" className="panic-day-tabs" role="tablist">
                {days.map((day) => (
                  <button
                    key={day.date}
                    aria-selected={activeDay?.date === day.date}
                    className={activeDay?.date === day.date ? "panic-day-tab is-selected" : "panic-day-tab"}
                    role="tab"
                    type="button"
                    onClick={() => {
                      setSelectedDay(day.date);
                      setSelectedStart(null);
                    }}
                  >
                    {dayTabLabel(day.date, timeZone)}
                  </button>
                ))}
              </div>
              <div className="panic-slot-grid">
                {(activeDay?.slots || []).map((slot) => (
                  <button
                    key={slot.start_at}
                    aria-pressed={selectedStart === slot.start_at}
                    className={selectedStart === slot.start_at ? "panic-slot-chip is-selected" : "panic-slot-chip"}
                    type="button"
                    onClick={() => setSelectedStart(slot.start_at)}
                  >
                    {formatSlotTime(slot.start_at, timeZone)}
                  </button>
                ))}
              </div>
            </>
          ) : (
            <p className="panic-empty-window">
              No open times in the next 48 hours.
              {availability.next_bookable_at
                ? ` The next bookable day is ${dayTabLabel(
                    dayKeyIn(timeZone, new Date(availability.next_bookable_at)),
                    timeZone,
                  )}.`
                : ""}
            </p>
          )
        ) : null}

        <label className="panic-note-label">
          A line for {coachFirstName} (optional)
          <input
            className="panic-note-input"
            maxLength={200}
            placeholder="What's got you stuck?"
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />
        </label>

        <button
          className="task-create-button panic-book-button"
          disabled={!selectedStart || booking.status === "booking"}
          type="button"
          onClick={() => selectedStart && book(selectedStart)}
        >
          {booking.status === "booking" ? "Booking..." : "Book it"}
        </button>

        {booking.status === "error" ? (
          <div className="panic-conflict" role="alert">
            <p>{booking.message}</p>
            {booking.suggestions?.length ? (
              <div className="panic-slot-grid">
                {booking.suggestions.map((iso) => (
                  <button
                    key={iso}
                    className="panic-slot-chip panic-suggestion-chip"
                    type="button"
                    onClick={() => book(iso)}
                  >
                    {formatWhen(iso, timeZone)}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </section>
    </main>
  );
}
