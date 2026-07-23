import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { apiClient } from "../api/client";
import { getErrorMessage } from "../api/utils";
import { useAuth } from "../auth/AuthContext";

const MORNING_WINDOWS = [
  ["6-8am", "6:00–8:00 am"],
  ["8-10am", "8:00–10:00 am"],
  ["10am-12pm", "10:00 am–12:00 pm"],
];
const EVENING_WINDOWS = [
  ["4-6pm", "4:00–6:00 pm"],
  ["6-8pm", "6:00–8:00 pm"],
  ["8-10pm", "8:00–10:00 pm"],
];
const CONTACT_METHODS = [
  ["whatsapp", "WhatsApp"],
  ["sms", "SMS (text message)"],
];

function getTimezoneOptions() {
  try {
    return Intl.supportedValuesOf("timeZone");
  } catch {
    return ["UTC"];
  }
}

function guessTimezone(options) {
  try {
    const guess = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return options.includes(guess) ? guess : "";
  } catch {
    return "";
  }
}

export function OnboardingPage() {
  const navigate = useNavigate();
  const { user, updateUser } = useAuth();
  const timezones = useMemo(getTimezoneOptions, []);

  const [formData, setFormData] = useState(() => ({
    timezone: guessTimezone(timezones),
    morning_window: "",
    evening_window: "",
    contact_method: "whatsapp",
    contact_number: "",
    help_topics: "",
  }));
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    let isMounted = true;
    apiClient
      .get("/onboarding/")
      .then((response) => {
        if (isMounted && response.data) {
          const saved = response.data;
          setFormData((current) => ({
            ...current,
            timezone: saved.timezone || current.timezone,
            morning_window: saved.morning_window || "",
            evening_window: saved.evening_window || "",
            contact_method: saved.contact_method || "whatsapp",
            contact_number: saved.contact_number || "",
            help_topics: saved.help_topics || "",
          }));
        }
      })
      .catch(() => {})
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  function setField(name, value) {
    setFormData((current) => ({ ...current, [name]: value }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setErrorMessage("");
    setIsSubmitting(true);
    try {
      await apiClient.put("/onboarding/", formData);
      if (user) updateUser({ ...user, onboarding_complete: true });
      navigate("/app", { replace: true });
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "We couldn't save your answers. Please try again."));
      setIsSubmitting(false);
    }
  }

  return (
    <main className="content-page">
      <section className="content-card onboarding-card">
        <p className="eyebrow">Welcome aboard</p>
        <h2>Tell us a little about you</h2>
        <p className="subtle-copy">
          Your answers help your coach hit the ground running. It takes about a minute — and you
          can come back to change anything later.
        </p>

        <form className="entity-form-grid onboarding-form" onSubmit={handleSubmit}>
          <label className="entity-form-wide">
            Your timezone
            <select
              value={formData.timezone}
              onChange={(event) => setField("timezone", event.target.value)}
              required
            >
              <option value="" disabled>
                Choose your timezone
              </option>
              {timezones.map((zone) => (
                <option key={zone} value={zone}>
                  {zone.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </label>
          <label>
            Preferred morning check-in
            <select
              value={formData.morning_window}
              onChange={(event) => setField("morning_window", event.target.value)}
              required
            >
              <option value="" disabled>
                Choose a window
              </option>
              {MORNING_WINDOWS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Preferred evening check-in
            <select
              value={formData.evening_window}
              onChange={(event) => setField("evening_window", event.target.value)}
              required
            >
              <option value="" disabled>
                Choose a window
              </option>
              {EVENING_WINDOWS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <fieldset className="entity-form-wide onboarding-contact-method">
            <legend>How should we text you?</legend>
            <div className="onboarding-contact-options">
              {CONTACT_METHODS.map(([value, label]) => (
                <label key={value} className="onboarding-contact-option">
                  <input
                    checked={formData.contact_method === value}
                    name="contact_method"
                    type="radio"
                    value={value}
                    onChange={() => setField("contact_method", value)}
                  />
                  {label}
                </label>
              ))}
            </div>
          </fieldset>
          <label className="entity-form-wide">
            {formData.contact_method === "whatsapp" ? "WhatsApp number" : "Phone number"}
            <input
              autoComplete="tel"
              maxLength={30}
              placeholder="+1 555 123 4567"
              type="tel"
              value={formData.contact_number}
              onChange={(event) => setField("contact_number", event.target.value)}
              required
            />
          </label>
          <label className="entity-form-wide">
            What do you want help with?
            <textarea
              placeholder="Mornings, follow-through, planning your day — whatever is on your mind."
              rows={4}
              value={formData.help_topics}
              onChange={(event) => setField("help_topics", event.target.value)}
            />
          </label>
          {errorMessage ? <p className="form-error entity-form-wide">{errorMessage}</p> : null}
          <div className="entity-form-actions entity-form-wide">
            <button className="task-create-button" disabled={isSubmitting || isLoading} type="submit">
              {isSubmitting ? "Saving..." : "Save and continue"}
            </button>
            <Link className="back-link onboarding-skip-link" to="/app">
              I&apos;ll do this later
            </Link>
          </div>
        </form>
      </section>
    </main>
  );
}
