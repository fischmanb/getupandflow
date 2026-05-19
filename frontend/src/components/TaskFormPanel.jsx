import { useEffect, useMemo, useRef, useState } from "react";

import { apiClient } from "../api/client";
import { getErrorMessage } from "../api/utils";
import { useAuth } from "../auth/AuthContext";
import { useClientFilter } from "../filters/ClientFilterContext";
import { useOutsideClick } from "../hooks/useOutsideClick";

function toLocalDateTimeValue(value) {
  if (!value) {
    return "";
  }
  return value.slice(0, 16);
}

function getInitialTaskState(task, defaultClientId) {
  return {
    title: task?.title || "",
    deadline: toLocalDateTimeValue(task?.deadline),
    description: task?.description || "",
    completed: Boolean(task?.completed_at),
    client_id: task?.client?.id || defaultClientId || "",
  };
}

export function TaskFormPanel({ onCancel, onSaved, task }) {
  const { user } = useAuth();
  const { selectedClients, selectedClientIds, supportsClientFiltering } = useClientFilter();
  const [errorMessage, setErrorMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formState, setFormState] = useState(() =>
    getInitialTaskState(task, selectedClientIds[0] || user?.id),
  );

  const initialFormState = useMemo(
    () => getInitialTaskState(task, selectedClientIds[0] || user?.id),
    [task, selectedClientIds, user?.id],
  );
  const isDirty = useMemo(
    () => JSON.stringify(formState) !== JSON.stringify(initialFormState),
    [formState, initialFormState],
  );

  const cardRef = useRef(null);
  function attemptCancel() {
    if (isDirty && !window.confirm("Discard your changes?")) {
      return;
    }
    onCancel();
  }
  useOutsideClick(cardRef, attemptCancel, true);

  const isClient = user?.role === "Client";
  const isCreateMode = !task;
  const eligibleClients = supportsClientFiltering ? selectedClients : [{ id: user.id, label: user.first_name || user.username }];
  const selectedClientId = supportsClientFiltering ? selectedClientIds[0] || "" : user?.id;

  useEffect(() => {
    setFormState(getInitialTaskState(task, selectedClientIds[0] || user?.id));
  }, [selectedClientIds, task, user?.id]);

  async function handleSubmit(submitEvent) {
    submitEvent.preventDefault();
    setErrorMessage("");
    setIsSubmitting(true);

    const payload = {
      ...formState,
      client_id: isClient ? user.id : Number(isCreateMode ? selectedClientId : formState.client_id),
      deadline: new Date(formState.deadline).toISOString(),
      completed_at: formState.completed ? new Date().toISOString() : null,
    };

    try {
      if (task) {
        await apiClient.put(`/tasks/${task.id}/`, payload);
      } else {
        await apiClient.post("/tasks/", payload);
      }
      onSaved();
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Unable to save task."));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="entity-form-card" ref={cardRef}>
      <div className="entity-form-header">
        <h4>{task ? "Edit task" : "New task"}</h4>
        <button aria-label="Close" className="entity-form-dismiss" onClick={attemptCancel} type="button">
          ×
        </button>
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
        <br></br>
        <label>
          Deadline
          <input
            required
            type="datetime-local"
            value={formState.deadline}
            onChange={(e) => setFormState((current) => ({ ...current, deadline: e.target.value }))}
          />
        </label>
        <label className="entity-form-wide">
          Description
          <textarea
            rows="4"
            value={formState.description}
            onChange={(e) => setFormState((current) => ({ ...current, description: e.target.value }))}
          />
        </label>
        {task ? (
          <label className="entity-form-wide checkbox-row">
            <input
              checked={formState.completed}
              onChange={(e) => setFormState((current) => ({ ...current, completed: e.target.checked }))}
              type="checkbox"
            />
            Mark task completed
          </label>
        ) : null}
        {errorMessage ? <p className="form-error entity-form-wide">{errorMessage}</p> : null}
        <div className="entity-form-actions entity-form-wide">
          <button className="task-create-button" disabled={isSubmitting} type="submit">
            {isSubmitting ? "Saving..." : task ? "Save task" : "Create task"}
          </button>
        </div>
      </form>
    </section>
  );
}
