import { Link } from "react-router-dom";

export function BillingSuccessPage() {
  return (
    <main className="auth-layout">
      <section className="auth-card billing-success-card">
        <p className="eyebrow">Payment confirmed</p>
        <h1>Welcome to Get Up and Flow!</h1>
        <p className="subtle-copy">
          Your subscription is set up and your account is being activated — that
          usually takes just a moment. Sign in with the email and password you
          chose during signup.
        </p>
        <Link className="task-create-button billing-success-cta" to="/login">
          Go to login
        </Link>
      </section>
    </main>
  );
}
