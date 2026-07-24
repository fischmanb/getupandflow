import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { format } from "date-fns";

import { apiClient } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { apiEventToRBC } from "../calendar/eventAdapter";
import { useBillingSubscription } from "../components/BillingCard";
import { useClientFilter } from "../filters/ClientFilterContext";

// Mirrors the value → label mapping used by the onboarding form selects.
const WINDOW_LABELS = {
  "6-8am": "6:00–8:00 am",
  "8-10am": "8:00–10:00 am",
  "10am-12pm": "10:00 am–12:00 pm",
  "4-6pm": "4:00–6:00 pm",
  "6-8pm": "6:00–8:00 pm",
  "8-10pm": "8:00–10:00 pm",
};

function getTimeGreeting(date = new Date()) {
  const hour = date.getHours();
  if (hour >= 5 && hour < 12) return "Good morning";
  if (hour >= 12 && hour < 18) return "Good afternoon";
  return "Good evening";
}

function getFirstName(user) {
  if (!user) return "";
  return user.first_name || user.username;
}

function MatchingCard() {
  return (
    <div className="coach-card matching-card">
      <div aria-hidden="true" className="coach-card-avatar matching-card-avatar">
        ~
      </div>
      <div className="coach-card-body">
        <h3 className="coach-card-name">Your coach is on the way</h3>
        <p className="matching-card-copy">
          We are matching you with your coach — guaranteed within 48 hours, usually within 12-24.
        </p>
      </div>
    </div>
  );
}

function OnboardingPrompt() {
  return (
    <div className="onboarding-prompt home-onboarding-nudge">
      <p>
        Tell us a little about you — your check-in preferences help your coach hit the ground
        running.
      </p>
      <Link className="task-create-button onboarding-prompt-cta" to="/app/onboarding">
        Complete onboarding
      </Link>
    </div>
  );
}

function CoachCard({ coach }) {
  if (!coach) {
    return <p className="subtle-copy home-coach-empty">Your coach will be introduced shortly.</p>;
  }

  return (
    <div className="coach-card">
      {coach.photo_url ? (
        <img alt={coach.name} className="coach-card-photo" src={coach.photo_url} />
      ) : (
        <div aria-hidden="true" className="coach-card-avatar">
          {(coach.name || "?").charAt(0).toUpperCase()}
        </div>
      )}
      <div className="coach-card-body">
        <h3 className="coach-card-name">{coach.name}</h3>
        {coach.bio ? (
          <div className="coach-card-about">
            <p className="coach-card-label">About your coach</p>
            <p className="coach-card-bio">{coach.bio}</p>
          </div>
        ) : null}
        {coach.contact_email || coach.contact_phone ? (
          <div className="coach-card-contacts">
            {coach.contact_email ? <a href={`mailto:${coach.contact_email}`}>{coach.contact_email}</a> : null}
            {coach.contact_phone ? <a href={`tel:${coach.contact_phone}`}>{coach.contact_phone}</a> : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

// Home keeps a quiet, single-line past-due notice (a failed payment interrupts
// service, so it stays visible here) but carries no billing controls — those
// live in Account Settings.
function PastDueNotice({ subscription }) {
  if (!subscription || subscription.status !== "past_due") return null;

  return (
    <p className="home-pastdue-notice" role="alert">
      There was a problem with your last payment —{" "}
      <Link to="/app/settings">review billing in account settings</Link>.
    </p>
  );
}

function RhythmSection({ prefs }) {
  const morning = prefs?.morning_window ? WINDOW_LABELS[prefs.morning_window] : null;
  const evening = prefs?.evening_window ? WINDOW_LABELS[prefs.evening_window] : null;

  const touchpoints = [
    {
      key: "jump-start",
      name: "Jump Start",
      when: morning ? `Mornings, ${morning}` : "Mornings",
      copy: "A short check-in to set up your day.",
    },
    {
      key: "reminders",
      name: "Reminders",
      when: "Through the day",
      copy: "Gentle nudges to keep things moving.",
    },
    {
      key: "panic-button",
      name: "Panic Button",
      when: "Whenever you need it",
      copy: (
        <>
          Up to 45 minutes with your coach when you feel stuck —{" "}
          <Link to="/app/calendar">open your calendar</Link>.
        </>
      ),
    },
    {
      key: "retro",
      name: "Retro",
      when: evening ? `Evenings, ${evening}` : "Evenings",
      copy: "10–20 minutes to look back and lock in what worked.",
    },
  ];

  return (
    <ul className="home-rhythm">
      {touchpoints.map((touchpoint) => (
        <li key={touchpoint.key}>
          <div className="home-rhythm-topline">
            <span className="home-rhythm-name">{touchpoint.name}</span>
            <span className="home-rhythm-when">{touchpoint.when}</span>
          </div>
          <p className="home-rhythm-copy">{touchpoint.copy}</p>
        </li>
      ))}
    </ul>
  );
}

function NextSessionLine({ events }) {
  const nextStart = useMemo(() => {
    const now = new Date();
    let earliest = null;
    for (const event of events || []) {
      try {
        const { start } = apiEventToRBC(event);
        if (start > now && (!earliest || start < earliest)) {
          earliest = start;
        }
      } catch {
        // Skip events the adapter can't parse.
      }
    }
    return earliest;
  }, [events]);

  // No upcoming session: omit the block entirely rather than show absence.
  if (!nextStart) return null;

  return (
    <p className="home-next-session">
      Next session: {format(nextStart, "EEEE, MMMM d")} at {format(nextStart, "h:mm aaa")} ·{" "}
      <Link to="/app/calendar">view calendar</Link>
    </p>
  );
}

export function HomePage() {
  const { user } = useAuth();
  const { events, isLoadingClients, selectedClients, supportsClientFiltering } = useClientFilter();

  // Billing state renders ONLY for the client viewing their own home -- never
  // in coach/admin mirror view (deliberate exception to mirroring).
  const isClientSelf = !supportsClientFiltering && user?.role === "Client";
  const subscription = useBillingSubscription(isClientSelf);

  // Check-in preferences come from the client's own onboarding answers, so
  // they are only available (and only fetched) on the client's own home.
  const [prefs, setPrefs] = useState(null);
  useEffect(() => {
    if (!isClientSelf) return undefined;
    let isMounted = true;
    apiClient
      .get("/onboarding/")
      .then((response) => {
        if (isMounted) setPrefs(response.data || null);
      })
      .catch(() => {
        if (isMounted) setPrefs(null);
      });
    return () => {
      isMounted = false;
    };
  }, [isClientSelf]);

  // Mirror-view: a coach/admin with one client selected sees exactly what that
  // client sees on their own home page (minus billing and onboarding state).
  let greetingName = null;
  let coach = null;
  let promptMessage = "";

  if (!supportsClientFiltering) {
    greetingName = getFirstName(user);
    coach = user?.my_coach || null;
  } else if (selectedClients.length === 1) {
    greetingName = (selectedClients[0].label || "").split(" ")[0];
    coach = selectedClients[0].coach || null;
  } else if (isLoadingClients) {
    promptMessage = "Loading your clients...";
  } else if (selectedClients.length === 0) {
    promptMessage = "Choose a client from the menu to see their home page.";
  } else {
    promptMessage = "Select a single client from the menu to see their home page.";
  }

  return (
    <main className="workspace-shell">
      <section className="home-grid">
        <section className="workspace-panel home-panel">
          {greetingName ? (
            <>
              {isClientSelf ? <PastDueNotice subscription={subscription} /> : null}
              <h2 className="home-greeting">
                {getTimeGreeting()}, {greetingName}
              </h2>
              <div className="home-coach-section">
                <p className="panel-label">Your coach</p>
                {isClientSelf && !coach ? <MatchingCard /> : <CoachCard coach={coach} />}
              </div>
              <div className="home-rhythm-section">
                <p className="panel-label">Your rhythm</p>
                <RhythmSection prefs={isClientSelf ? prefs : null} />
                {isClientSelf && user?.onboarding_complete === false ? <OnboardingPrompt /> : null}
              </div>
              <NextSessionLine events={events} />
              <Link className="task-create-button home-calendar-launcher" to="/app/calendar">
                Open calendar
              </Link>
              {isClientSelf ? (
                <footer className="home-panel-footer">
                  <Link className="home-footer-link" to="/app/settings">
                    Account &amp; billing
                  </Link>
                </footer>
              ) : null}
            </>
          ) : (
            <div className="selection-prompt">
              <h4>Select a client</h4>
              <p className="subtle-copy">{promptMessage}</p>
            </div>
          )}
        </section>
      </section>
    </main>
  );
}
