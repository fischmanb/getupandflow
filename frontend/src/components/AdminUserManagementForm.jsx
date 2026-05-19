import { useEffect, useMemo, useState } from "react";

function getInitialState(user, defaultRole = "Coach") {
  return {
    username: user?.username || "",
    first_name: user?.first_name || "",
    last_name: user?.last_name || "",
    email: user?.email || "",
    role: user?.role || defaultRole,
    assigned_coach_id: user?.assigned_coach_id || "",
    phone_number: user?.phone_number || "",
    password: "",
  };
}

export function AdminUserManagementForm({
  coaches,
  editingUser,
  errorMessage,
  isLoadingCoaches,
  isSubmitting,
  onCancel,
  onSubmit,
}) {
  const [formState, setFormState] = useState(() => getInitialState(editingUser));

  useEffect(() => {
    setFormState(getInitialState(editingUser));
  }, [editingUser]);

  const initialFormState = useMemo(() => getInitialState(editingUser), [editingUser]);
  const isDirty = useMemo(
    () => JSON.stringify(formState) !== JSON.stringify(initialFormState),
    [formState, initialFormState],
  );

  function attemptCancel() {
    if (!onCancel) return;
    if (isDirty && !window.confirm("Discard your changes?")) {
      return;
    }
    onCancel();
  }

  const isClient = formState.role === "Client";

  return (
    <section className="entity-form-card">
      <div className="entity-form-header">
        <div>
          <p className="eyebrow">Admin User Management</p>
          <h3>{editingUser ? "Update user" : "Create user"}</h3>
        </div>
        {editingUser ? (
          <button aria-label="Close" className="entity-form-dismiss" onClick={attemptCancel} type="button">
            ×
          </button>
        ) : null}
      </div>

      <form
        className="entity-form-grid"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit(formState);
        }}
      >
        <label>
          Role
          <select
            value={formState.role}
            onChange={(event) =>
              setFormState((current) => ({
                ...current,
                role: event.target.value,
                assigned_coach_id: event.target.value === "Client" ? current.assigned_coach_id : "",
              }))
            }
          >
            <option value="Coach">Coach</option>
            <option value="Client">Client</option>
          </select>
        </label>
        <label>
          Username
          <input
            required
            value={formState.username}
            onChange={(event) => setFormState((current) => ({ ...current, username: event.target.value }))}
          />
        </label>
        <label>
          First name
          <input
            value={formState.first_name}
            onChange={(event) => setFormState((current) => ({ ...current, first_name: event.target.value }))}
          />
        </label>
        <label>
          Last name
          <input
            value={formState.last_name}
            onChange={(event) => setFormState((current) => ({ ...current, last_name: event.target.value }))}
          />
        </label>
        <label>
          Email
          <input
            type="email"
            value={formState.email}
            onChange={(event) => setFormState((current) => ({ ...current, email: event.target.value }))}
          />
        </label>
        <label>
          Phone number
          <input
            value={formState.phone_number}
            onChange={(event) => setFormState((current) => ({ ...current, phone_number: event.target.value }))}
          />
        </label>
        <label>
          {editingUser ? "New password (optional)" : "Password"}
          <input
            required={!editingUser}
            type="password"
            value={formState.password}
            onChange={(event) => setFormState((current) => ({ ...current, password: event.target.value }))}
          />
        </label>
        {isClient ? (
          <label>
            Assigned coach
            <select
              disabled={isLoadingCoaches}
              required
              value={formState.assigned_coach_id}
              onChange={(event) => setFormState((current) => ({ ...current, assigned_coach_id: event.target.value }))}
            >
              <option value="">{isLoadingCoaches ? "Loading coaches..." : "Select coach"}</option>
              {coaches.map((coach) => (
                <option key={coach.id} value={coach.id}>
                  {[coach.first_name, coach.last_name].filter(Boolean).join(" ") || coach.username}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        {errorMessage ? <p className="form-error entity-form-wide">{errorMessage}</p> : null}
        <div className="entity-form-actions entity-form-wide">
          <button className="task-create-button" disabled={isSubmitting} type="submit">
            {isSubmitting ? "Saving..." : editingUser ? "Save user" : "Create user"}
          </button>
        </div>
      </form>
    </section>
  );
}
