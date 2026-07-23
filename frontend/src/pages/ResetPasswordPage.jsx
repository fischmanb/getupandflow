import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { apiClient } from "../api/client";
import { getErrorMessage } from "../api/utils";

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const uid = searchParams.get("uid") || "";
  const token = searchParams.get("token") || "";

  const [formData, setFormData] = useState({ password: "", confirm: "" });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [wasReset, setWasReset] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const hasValidLink = Boolean(uid && token);

  async function handleSubmit(event) {
    event.preventDefault();
    setErrorMessage("");
    if (formData.password !== formData.confirm) {
      setErrorMessage("The passwords don't match.");
      return;
    }
    setIsSubmitting(true);
    try {
      await apiClient.post("/auth/password-reset/confirm/", {
        uid,
        token,
        new_password: formData.password,
      });
      setWasReset(true);
    } catch (error) {
      setErrorMessage(
        getErrorMessage(error, "We couldn't reset your password. Please request a new link."),
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-layout">
      <section className="auth-card">
        <h1>Choose a new password</h1>
        {!hasValidLink ? (
          <>
            <p className="form-error">
              This reset link looks incomplete. Please use the link from your email, or request a
              new one.
            </p>
            <p className="subtle-copy">
              <Link className="back-link" to="/forgot-password">
                Request a new link
              </Link>
            </p>
          </>
        ) : wasReset ? (
          <>
            <p className="subtle-copy">Your password has been reset. You can now log in.</p>
            <p className="subtle-copy">
              <Link className="back-link" to="/login">
                Go to login
              </Link>
            </p>
          </>
        ) : (
          <form className="auth-form" onSubmit={handleSubmit}>
            <label>
              New password
              <input
                autoComplete="new-password"
                minLength={8}
                name="password"
                type="password"
                value={formData.password}
                onChange={(event) =>
                  setFormData((current) => ({ ...current, password: event.target.value }))
                }
                required
              />
            </label>
            <label>
              Confirm new password
              <input
                autoComplete="new-password"
                minLength={8}
                name="confirm"
                type="password"
                value={formData.confirm}
                onChange={(event) =>
                  setFormData((current) => ({ ...current, confirm: event.target.value }))
                }
                required
              />
            </label>
            {errorMessage ? <p className="form-error">{errorMessage}</p> : null}
            <button disabled={isSubmitting} type="submit">
              {isSubmitting ? "Saving..." : "Reset password"}
            </button>
          </form>
        )}
      </section>
    </main>
  );
}
