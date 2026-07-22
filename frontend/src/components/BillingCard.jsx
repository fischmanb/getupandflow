import { useEffect, useState } from "react";
import { format } from "date-fns";

import { apiClient } from "../api/client";
import { getErrorMessage } from "../api/utils";

export const INTERVAL_UNITS = { monthly: "month", weekly: "week" };

const PORTAL_ACTIONS = [
  ["payment_method_update", "Update payment method"],
  ["subscription_update", "Change plan"],
  ["subscription_cancel", "Cancel plan"],
];

export function useBillingSubscription(enabled) {
  const [subscription, setSubscription] = useState(null);

  useEffect(() => {
    if (!enabled) return undefined;
    let isMounted = true;
    apiClient
      .get("/billing/subscription/")
      .then((response) => {
        if (isMounted) setSubscription(response.data);
      })
      .catch(() => {
        if (isMounted) setSubscription(null);
      });
    return () => {
      isMounted = false;
    };
  }, [enabled]);

  return subscription;
}

async function redirectToPortal(flow) {
  const response = await apiClient.post("/billing/portal/", { flow });
  window.location.href = response.data.url;
}

function formatPeriodEnd(subscription) {
  if (!subscription.current_period_end) return null;
  return format(new Date(subscription.current_period_end), "MMMM d, yyyy");
}

function getStatusChip(subscription) {
  const endDate = formatPeriodEnd(subscription);
  if (subscription.status === "past_due") {
    return { label: "Payment issue", className: "status-chip status-chip-past-due" };
  }
  if (subscription.status === "canceled") {
    return { label: "Canceled", className: "status-chip status-chip-canceled" };
  }
  if (subscription.cancel_at_period_end) {
    return {
      label: endDate ? `Ends ${endDate}` : "Ends at period end",
      className: "status-chip status-chip-ending",
    };
  }
  if (subscription.status === "active") {
    return { label: "Active", className: "status-chip status-chip-active" };
  }
  return { label: subscription.status, className: "status-chip" };
}

export function PastDueBanner({ subscription }) {
  const [isDismissed, setIsDismissed] = useState(false);
  const [isRedirecting, setIsRedirecting] = useState(false);

  if (!subscription || subscription.status !== "past_due" || isDismissed) return null;

  async function handleUpdatePaymentMethod() {
    setIsRedirecting(true);
    try {
      await redirectToPortal("payment_method_update");
    } catch {
      setIsRedirecting(false);
    }
  }

  return (
    <div className="billing-alert" role="alert">
      <p>
        There was a problem with your last payment —{" "}
        <button
          className="billing-alert-link"
          disabled={isRedirecting}
          onClick={handleUpdatePaymentMethod}
          type="button"
        >
          update your payment method
        </button>
        .
      </p>
      <button
        aria-label="Dismiss"
        className="billing-alert-dismiss"
        onClick={() => setIsDismissed(true)}
        type="button"
      >
        ×
      </button>
    </div>
  );
}

export function BillingCard({ subscription }) {
  const [errorMessage, setErrorMessage] = useState("");
  const [pendingFlow, setPendingFlow] = useState(null);

  if (!subscription) return null;

  async function openPortal(flow) {
    setErrorMessage("");
    setPendingFlow(flow ?? "portal");
    try {
      await redirectToPortal(flow);
    } catch (error) {
      setErrorMessage(
        getErrorMessage(error, "We could not open billing management. Please try again."),
      );
      setPendingFlow(null);
    }
  }

  const chip = getStatusChip(subscription);
  const endDate = formatPeriodEnd(subscription);
  const priceUnit = INTERVAL_UNITS[subscription.interval] || subscription.interval;
  const cardOnFile = subscription.card_last4
    ? `${subscription.card_brand ? subscription.card_brand.charAt(0).toUpperCase() + subscription.card_brand.slice(1) : "Card"} •••• ${subscription.card_last4}`
    : "—";
  let renewalLabel = "Renews";
  if (subscription.status === "canceled") {
    renewalLabel = "Ended";
  } else if (subscription.cancel_at_period_end) {
    renewalLabel = "Ends";
  }

  return (
    <div className="home-billing-section">
      <p className="panel-label">Billing</p>
      <div className="billing-card">
        <div className="billing-card-header">
          <div>
            <h3 className="billing-card-plan">{subscription.plan_name}</h3>
            {subscription.amount ? (
              <p className="billing-card-price">
                ${subscription.amount}
                <span className="billing-card-unit">/{priceUnit}</span>
              </p>
            ) : null}
          </div>
          <span className={chip.className}>{chip.label}</span>
        </div>
        <dl className="billing-card-facts">
          <div>
            <dt>Payment method</dt>
            <dd>{cardOnFile}</dd>
          </div>
          <div>
            <dt>{renewalLabel}</dt>
            <dd>{endDate || "—"}</dd>
          </div>
        </dl>
        {errorMessage ? <p className="form-error">{errorMessage}</p> : null}
        {subscription.status !== "canceled" ? (
          <div className="billing-card-actions">
            {PORTAL_ACTIONS.map(([flow, label]) => (
              <button
                key={flow}
                className="secondary-button"
                disabled={Boolean(pendingFlow)}
                onClick={() => openPortal(flow)}
                type="button"
              >
                {label}
              </button>
            ))}
          </div>
        ) : null}
        <button
          className="back-link billing-manage-link"
          disabled={Boolean(pendingFlow)}
          onClick={() => openPortal(null)}
          type="button"
        >
          Manage billing
        </button>
      </div>
    </div>
  );
}
