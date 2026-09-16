import { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { apiClient } from "../api/client";

const ADS_ID = import.meta.env.VITE_GOOGLE_ADS_ID || "";
const PURCHASE_LABEL = import.meta.env.VITE_GOOGLE_ADS_PURCHASE_LABEL || "";

export function BillingSuccessPage() {
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const sessionId = searchParams.get("session_id") || "";
    if (!sessionId || typeof window.gtag !== "function") return;
    let cancelled = false;
    // GA4 `purchase` is what the Google Ads conversion action imports. The
    // amount comes from Stripe via the API, never from the client, and the
    // Stripe session id is the transaction_id so a reload dedupes rather than
    // counting a second sale.
    apiClient
      .get("/billing/checkout-session/", { params: { session_id: sessionId } })
      .then(({ data }) => {
        if (cancelled) return;
        window.gtag("event", "purchase", {
          transaction_id: data.transaction_id,
          value: data.value,
          currency: data.currency,
          items: (data.items || []).map((id) => ({ item_id: id, item_name: id, quantity: 1 })),
        });
        if (ADS_ID && PURCHASE_LABEL) {
          window.gtag("event", "conversion", {
            send_to: `${ADS_ID}/${PURCHASE_LABEL}`,
            transaction_id: data.transaction_id,
            value: data.value,
            currency: data.currency,
          });
        }
      })
      .catch(() => {
        // Analytics must never affect the buyer; a failed lookup just means
        // no event. The subscription itself was confirmed by Stripe already.
      });
    return () => {
      cancelled = true;
    };
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
