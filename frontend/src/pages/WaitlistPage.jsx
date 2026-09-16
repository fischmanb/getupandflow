import { Link, useLocation } from "react-router-dom";

/** Shown instead of Stripe when the applicant's timezone is outside coverage.
 *
 * The entry is already saved by the time we land here; this page only explains.
 */
export function WaitlistPage() {
  const { state } = useLocation();
  const timezone = state?.timezone || "";
  const zoneLabel = timezone ? timezone.replace(/_/g, " ").replace("/", " / ") : "your time zone";

  return (
    <main className="auth-layout">
      <section className="auth-card waitlist-card">
        <p className="eyebrow">You're on the list</p>
        <h1>We're coming to {zoneLabel}</h1>
        <p className="subtle-copy">
          We have your application. Right now our coaches work an 8am&ndash;5pm Eastern
          day, so we can't give you the full daily rhythm in your hours yet &mdash; and we'd
          rather tell you that than sell you half a service.
        </p>
        <p className="subtle-copy">
          We're adding coaches in more time zones over the coming weeks. You'll hear from
          us at the email you gave us the moment we can cover your workday. Nothing was
          charged.
        </p>
        <Link className="task-create-button" to="/login">
          Back to Get Up and Flow
        </Link>
      </section>
    </main>
  );
}
