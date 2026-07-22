import { useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "../api/client";
import { getErrorMessage } from "../api/utils";
import { useAuth } from "../auth/AuthContext";

function getDisplayName(user) {
  return [user.first_name, user.last_name].filter(Boolean).join(" ") || user.username;
}

function CoachProfileForm() {
  const { user, updateUser } = useAuth();
  const profile = user.profile || {};
  const [formState, setFormState] = useState({
    bio: profile.bio || "",
    contact_email: profile.contact_email || "",
    contact_phone: profile.contact_phone || "",
  });
  const [photoFile, setPhotoFile] = useState(null);
  const [photoPreviewUrl, setPhotoPreviewUrl] = useState(profile.photo_url || null);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  function handlePhotoChange(event) {
    const file = event.target.files?.[0] || null;
    setPhotoFile(file);
    setPhotoPreviewUrl(file ? URL.createObjectURL(file) : profile.photo_url || null);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setErrorMessage("");
    setSuccessMessage("");
    setIsSubmitting(true);

    try {
      const payload = new FormData();
      payload.append("bio", formState.bio);
      payload.append("contact_email", formState.contact_email);
      payload.append("contact_phone", formState.contact_phone);
      if (photoFile) {
        payload.append("photo", photoFile);
      }

      const response = await apiClient.patch("/auth/me/", payload);
      updateUser(response.data);
      setPhotoFile(null);
      setPhotoPreviewUrl(response.data.profile?.photo_url || null);
      setSuccessMessage("Profile saved.");
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "We couldn't save your profile right now."));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="entity-form-card">
      <div className="entity-form-header">
        <div>
          <p className="eyebrow">Coach Profile</p>
          <h3>How clients see you</h3>
        </div>
      </div>

      <form className="entity-form-grid" onSubmit={handleSubmit}>
        <div className="entity-form-wide profile-photo-row">
          {photoPreviewUrl ? (
            <img alt="Profile preview" className="coach-card-photo" src={photoPreviewUrl} />
          ) : (
            <div aria-hidden="true" className="coach-card-avatar">
              {getDisplayName(user).charAt(0).toUpperCase()}
            </div>
          )}
          <label className="profile-photo-input">
            Photo
            <input accept="image/*" type="file" onChange={handlePhotoChange} />
          </label>
        </div>
        <label className="entity-form-wide">
          Bio
          <textarea
            placeholder="A short introduction your clients will see."
            rows={4}
            value={formState.bio}
            onChange={(event) => setFormState((current) => ({ ...current, bio: event.target.value }))}
          />
        </label>
        <label>
          Contact email
          <input
            type="email"
            value={formState.contact_email}
            onChange={(event) => setFormState((current) => ({ ...current, contact_email: event.target.value }))}
          />
        </label>
        <label>
          Contact phone
          <input
            value={formState.contact_phone}
            onChange={(event) => setFormState((current) => ({ ...current, contact_phone: event.target.value }))}
          />
        </label>
        {errorMessage ? <p className="form-error entity-form-wide">{errorMessage}</p> : null}
        {successMessage ? <p className="subtle-copy entity-form-wide">{successMessage}</p> : null}
        <div className="entity-form-actions entity-form-wide">
          <button className="task-create-button" disabled={isSubmitting} type="submit">
            {isSubmitting ? "Saving..." : "Save profile"}
          </button>
        </div>
      </form>
    </section>
  );
}

export function AccountSettingsPage() {
  const { user } = useAuth();
  const canEditCoachProfile = user.role === "Coach" || user.role === "Admin";

  return (
    <main className="content-page">
      <section className="content-card">
        <Link className="back-link" to="/app">← Back</Link>
        <p className="eyebrow">Account Settings</p>
        <h2>Your account</h2>
        <dl className="details-grid">
          <div>
            <dt>Name</dt>
            <dd>{getDisplayName(user)}</dd>
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
        {canEditCoachProfile ? <CoachProfileForm /> : null}
        <Link className="task-create-button category-manage-link" to="/app/categories">
          Manage event categories
        </Link>
      </section>
    </main>
  );
}
