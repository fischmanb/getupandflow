import { Link } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { BillingCard, PastDueBanner, useBillingSubscription } from "../components/BillingCard";
import { useClientFilter } from "../filters/ClientFilterContext";

function getDisplayName(user) {
  if (!user) return "";
  return [user.first_name, user.last_name].filter(Boolean).join(" ") || user.username;
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

export function HomePage() {
  const { user } = useAuth();
  const { isLoadingClients, selectedClients, supportsClientFiltering } = useClientFilter();

  // Billing renders ONLY for the client viewing their own home -- never in
  // coach/admin mirror view (deliberate exception to mirroring).
  const isClientSelf = !supportsClientFiltering && user?.role === "Client";
  const subscription = useBillingSubscription(isClientSelf);

  // Mirror-view: a coach/admin with one client selected sees exactly what that
  // client sees on their own home page.
  let greetingName = null;
  let coach = null;
  let promptMessage = "";

  if (!supportsClientFiltering) {
    greetingName = getDisplayName(user);
    coach = user?.my_coach || null;
  } else if (selectedClients.length === 1) {
    greetingName = selectedClients[0].label;
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
              {isClientSelf ? <PastDueBanner subscription={subscription} /> : null}
              <h2 className="home-greeting">Welcome, {greetingName}</h2>
              <div className="home-coach-section">
                <p className="panel-label">Your coach</p>
                <CoachCard coach={coach} />
              </div>
              {isClientSelf ? <BillingCard subscription={subscription} /> : null}
              <Link className="task-create-button home-calendar-launcher" to="/app/calendar">
                Open calendar
              </Link>
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
