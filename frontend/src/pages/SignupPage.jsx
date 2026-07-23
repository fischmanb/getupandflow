import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { apiClient } from "../api/client";
import { getErrorMessage } from "../api/utils";
import { INTERVAL_UNITS } from "../components/BillingCard";

const PLAN_IDS = ["full_support", "focus_lite"];
const INTERVALS = ["monthly", "weekly"];
const INTERVAL_LABELS = { monthly: "Monthly", weekly: "Weekly" };

function normalizeChoice(value, allowed, fallback) {
  return allowed.includes(value) ? value : fallback;
}

export function SignupPage() {
  const [searchParams] = useSearchParams();
  const [plans, setPlans] = useState(null);
  const [catalogError, setCatalogError] = useState("");
  const [plan, setPlan] = useState(normalizeChoice(searchParams.get("plan"), PLAN_IDS, "full_support"));
  const [interval, setInterval] = useState(
    normalizeChoice(searchParams.get("interval"), INTERVALS, "monthly"),
  );
  const [formData, setFormData] = useState({ full_name: "", email: "", password: "" });
  const [errorMessage, setErrorMessage] = useState("");
  const [showLoginLink, setShowLoginLink] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    let isMounted = true;
    apiClient
      .get("/billing/config/")
      .then((response) => {
        if (isMounted) setPlans(response.data.plans);
      })
      .catch((error) => {
        if (isMounted) setCatalogError(getErrorMessage(error, "We could not load the plans. Please refresh."));
      });
    return () => {
      isMounted = false;
    };
  }, []);

  function handleChange(event) {
    const { name, value } = event.target;
    setFormData((current) => ({ ...current, [name]: value }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setErrorMessage("");
    setShowLoginLink(false);
    setIsSubmitting(true);
    try {
      const response = await apiClient.post("/billing/checkout/", {
        ...formData,
        plan,
        interval,
      });
      window.location.href = response.data.url;
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "We could not start checkout. Please try again."));
      setShowLoginLink(error?.response?.status === 409);
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-layout">
      <section className="auth-card signup-card">
        <p className="eyebrow">Get Up and Flow</p>
        <h1>Create your account</h1>
        <p className="subtle-copy">Pick a plan, then set up your login. You'll finish payment securely on Stripe.</p>

        <div aria-label="Billing period" className="interval-toggle" role="group">
          {INTERVALS.map((value) => (
            <button
              key={value}
              aria-pressed={interval === value}
              className={interval === value ? "is-selected" : ""}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => setInterval(value)}
              type="button"
            >
              {INTERVAL_LABELS[value]}
            </button>
          ))}
        </div>

        {catalogError ? <p className="form-error">{catalogError}</p> : null}
        <div className="plan-picker">
          {(plans || []).map((planOption) => (
            <button
              key={planOption.id}
              aria-pressed={plan === planOption.id}
              className={`plan-option${plan === planOption.id ? " is-selected" : ""}${planOption.featured ? " is-featured" : ""}`}
              onClick={() => setPlan(planOption.id)}
              onMouseDown={(event) => event.preventDefault()}
              type="button"
            >
              {planOption.badge ? <span className="plan-option-badge">{planOption.badge}</span> : null}
              <span className="plan-option-name">{planOption.name}</span>
              {planOption.tagline ? <span className="plan-option-tagline">{planOption.tagline}</span> : null}
              <span className="plan-option-price">
                ${planOption.prices[interval].amount}
                <span className="plan-option-unit">/{INTERVAL_UNITS[interval]}</span>
              </span>
              {planOption.value_note ? <span className="plan-option-value">{planOption.value_note}</span> : null}
              {(planOption.highlights || []).length ? (
                <ul className="plan-option-highlights">
                  {planOption.highlights.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ) : null}
              {planOption.footnote ? <span className="plan-option-footnote">{planOption.footnote}</span> : null}
            </button>
          ))}
          {!plans && !catalogError ? <p className="subtle-copy">Loading plans...</p> : null}
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label>
            Full name
            <input
              autoComplete="name"
              maxLength={150}
              name="full_name"
              value={formData.full_name}
              onChange={handleChange}
              required
            />
          </label>
          <label>
            Email
            <input
              autoComplete="email"
              name="email"
              type="email"
              value={formData.email}
              onChange={handleChange}
              required
            />
          </label>
          <label>
            Password
            <input
              autoComplete="new-password"
              name="password"
              type="password"
              minLength={8}
              value={formData.password}
              onChange={handleChange}
              required
            />
          </label>
          {errorMessage ? <p className="form-error">{errorMessage}</p> : null}
          {showLoginLink ? (
            <p className="subtle-copy">
              <Link className="back-link" to="/login">
                Log in to your account
              </Link>
            </p>
          ) : null}
          <button disabled={isSubmitting || !plans} type="submit">
            {isSubmitting ? "Redirecting to Stripe..." : "Continue to payment"}
          </button>
        </form>
        <p className="subtle-copy signup-footnote">
          Already have an account?{" "}
          <Link className="back-link" to="/login">
            Log in
          </Link>
        </p>
      </section>
    </main>
  );
}
