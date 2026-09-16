import { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";

const ADS_ID = import.meta.env.VITE_GOOGLE_ADS_ID || "";
const PURCHASE_LABEL = import.meta.env.VITE_GOOGLE_ADS_PURCHASE_LABEL || "";

export function BillingSuccessPage() {
  const [searchParams] = useSearchParams();

  useEffect(() => {
    // Purchase conversion. Reported here rather than inferred from a URL
    // pattern, and keyed on the Stripe session id so Google dedupes a reload
    // instead of counting a second sale. Inert until both ids are configured.
    if (!ADS_ID || !PURCHASE_LABEL || typeof window.gtag !== "function") return;
    window.gtag("event", "conversion", {
      send_to: `${ADS_ID}/${PURCHASE_LABEL}`,
      transaction_id: searchParams.get("session_id") || "",
    });
  }, [searchParams]);

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
