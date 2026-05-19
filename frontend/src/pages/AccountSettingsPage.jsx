import { Link } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

export function AccountSettingsPage() {
  const { user } = useAuth();

  return (
    <main className="content-page">
      <section className="content-card">
        <p className="eyebrow">Account Settings</p>
        <h2>Your account</h2>
        <p className="subtle-copy">Account settings will live here. Coming soon.</p>
        <dl className="details-grid">
          <div>
            <dt>Name</dt>
            <dd>{[user.first_name, user.last_name].filter(Boolean).join(" ") || user.username}</dd>
          </div>
          <div>
            <dt>Email</dt>
            <dd>{user.email || "Not provided"}</dd>
          </div>
          <div>
            <dt>Role</dt>
            <dd>{user.role}</dd>
          </div>
        </dl>
        {user.role === "Client" ? (
          <Link className="task-create-button category-manage-link" to="/app/categories">
            Manage event categories
          </Link>
        ) : null}
      </section>
    </main>
  );
}
