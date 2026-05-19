import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "../api/client";
import { fetchAllPages, getErrorMessage } from "../api/utils";
import { useAuth } from "../auth/AuthContext";
import { getCategoryColorHex } from "../categories/presetColors";
import { useClientFilter } from "../filters/ClientFilterContext";

function getInitialEventState(event, defaultClientId, initialDate = "") {
  return {
    title: event?.title || "",
    event_date: event?.event_date || initialDate || "",
    start_time: event?.start_time?.slice(0, 5) || "",
    end_time: event?.end_time?.slice(0, 5) || "",
    location: event?.location || "",
    description: event?.description || "",
    category: event?.category || "",
    recurrence_type: event?.recurrence_type || "none",
    recurrence_until: event?.recurrence_until || "",
    client_id: event?.client?.id || defaultClientId || "",
  };
}

export function EventFormPanel({ event, initialDate, onCancel, onSaved }) {
  const { user } = useAuth();
  const { selectedClients, selectedClientIds, supportsClientFiltering } = useClientFilter();
  const [categories, setCategories] = useState([]);
  const [errorMessage, setErrorMessage] = useState("");
  const [categoryError, setCategoryError] = useState("");
  const [isLoadingCategories, setIsLoadingCategories] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formState, setFormState] = useState(() =>
    getInitialEventState(event, selectedClientIds[0] || user?.id, initialDate),
  );

  const isClient = user?.role === "Client";
  const isCreateMode = !event;
  const eligibleClients = supportsClientFiltering ? selectedClients : [{ id: user.id, label: user.first_name || user.username }];
  const selectedClientId = supportsClientFiltering ? selectedClientIds[0] || "" : user?.id;
  const activeClientId = isClient ? user?.id : isCreateMode ? selectedClientId : formState.client_id;

  useEffect(() => {
    let isMounted = true;

    async function loadCategories() {
      setIsLoadingCategories(true);
      setCategoryError("");
      try {
        const params = activeClientId ? { client_id: activeClientId } : undefined;
        const categoryResults = await fetchAllPages("/categories/", { params });
        if (!isMounted) {
          return;
        }
        setCategories(categoryResults);
        if (formState.category && !categoryResults.some((category) => category.id === Number(formState.category))) {
          setFormState((current) => ({ ...current, category: "" }));
        }
      } catch (error) {
        if (isMounted) {
          setCategories([]);
          setCategoryError(getErrorMessage(error, "We couldn't load event categories."));
        }
      } finally {
        if (isMounted) {
          setIsLoadingCategories(false);
        }
      }
    }

    if (activeClientId) {
      loadCategories();
    } else {
      setCategories([]);
    }
    return () => {
      isMounted = false;
    };
  }, [activeClientId]);

  useEffect(() => {
    setFormState(getInitialEventState(event, selectedClientIds[0] || user?.id, initialDate));
  }, [event, initialDate, selectedClientIds, user?.id]);

  async function handleSubmit(submitEvent) {
    submitEvent.preventDefault();
    setErrorMessage("");
    setIsSubmitting(true);

    const payload = {
      ...formState,
      client_id: isClient ? user.id : Number(isCreateMode ? selectedClientId : formState.client_id),
      category: Number(formState.category),
      start_time: `${formState.start_time}:00`,
      end_time: `${formState.end_time}:00`,
      recurrence_until: formState.recurrence_type === "none" ? null : formState.recurrence_until,
    };

    try {
      if (event) {
        await apiClient.put(`/events/${event.id}/`, payload);
      } else {
        await apiClient.post("/events/", payload);
      }
      onSaved();
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Unable to save event."));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="entity-form-card">
      <div className="entity-form-header">
        <h4>{event ? "Edit event" : "New event"}</h4>
      </div>
      <form className="entity-form-grid" onSubmit={handleSubmit}>
        <label>
          Title
          <input
            required
            value={formState.title}
            onChange={(e) => setFormState((current) => ({ ...current, title: e.target.value }))}
          />
        </label>
        <label>
          Date
          <input
            required
            type="date"
            value={formState.event_date}
            onChange={(e) => setFormState((current) => ({ ...current, event_date: e.target.value }))}
          />
        </label>
        <label>
          Start time
          <input
            required
            type="time"
            value={formState.start_time}
            onChange={(e) => setFormState((current) => ({ ...current, start_time: e.target.value }))}
          />
        </label>
        <label>
          End time
          <input
            required
            type="time"
            value={formState.end_time}
            onChange={(e) => setFormState((current) => ({ ...current, end_time: e.target.value }))}
          />
        </label>
        <label>
          Location
          <input
            value={formState.location}
            onChange={(e) => setFormState((current) => ({ ...current, location: e.target.value }))}
          />
        </label>
        <label>
          Category
          <select
            disabled={isLoadingCategories}
            required
            value={formState.category}
            onChange={(e) => setFormState((current) => ({ ...current, category: e.target.value }))}
          >
            <option value="">{isLoadingCategories ? "Loading categories..." : "Select category"}</option>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name} ({category.color})
              </option>
            ))}
          </select>
        </label>
        <label>
          Recurrence
          <select
            value={formState.recurrence_type}
            onChange={(e) =>
              setFormState((current) => ({
                ...current,
                recurrence_type: e.target.value,
                recurrence_until: e.target.value === "none" ? "" : current.recurrence_until,
              }))
            }
          >
            <option value="none">Does not repeat</option>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
          </select>
        </label>
        {formState.recurrence_type !== "none" ? (
          <label>
            Repeat until
            <input
              required
              type="date"
              value={formState.recurrence_until}
              onChange={(e) => setFormState((current) => ({ ...current, recurrence_until: e.target.value }))}
            />
          </label>
        ) : null}
        {!isClient && !isCreateMode ? (
          <label>
            Client
            <select
              required
              value={formState.client_id}
              onChange={(e) => setFormState((current) => ({ ...current, client_id: e.target.value }))}
            >
              <option value="">Select client</option>
              {eligibleClients.map((client) => (
                <option key={client.id} value={client.id}>
                  {client.label}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <label className="entity-form-wide">
          Description
          <textarea
            rows="4"
            value={formState.description}
            onChange={(e) => setFormState((current) => ({ ...current, description: e.target.value }))}
          />
        </label>
        {isClient ? (
          <div className="entity-form-wide category-helper-row">
            <p className="subtle-copy">
              Need a new event category? Manage your preset colors on the categories page.
            </p>
            <Link className="task-create-button category-manage-link" to="/app/categories">
              Manage categories
            </Link>
          </div>
        ) : null}
        {categoryError ? <p className="form-error entity-form-wide">{categoryError}</p> : null}
        {categories.length > 0 ? (
          <div className="entity-form-wide category-option-preview">
            {categories.map((category) => (
              <span key={category.id} className="category-preview-pill">
                <span
                  className="category-swatch"
                  style={{ background: getCategoryColorHex(category.color) }}
                />
                {category.name}
              </span>
            ))}
          </div>
        ) : null}
        {errorMessage ? <p className="form-error entity-form-wide">{errorMessage}</p> : null}
        <div className="entity-form-actions entity-form-wide">
          <button className="task-create-button" disabled={isSubmitting} type="submit">
            {isSubmitting ? "Saving..." : event ? "Save event" : "Create event"}
          </button>
        </div>
      </form>
    </section>
  );
}
