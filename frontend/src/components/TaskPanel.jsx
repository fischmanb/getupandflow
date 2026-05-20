import { useEffect, useMemo, useRef, useState } from "react";

import { apiClient } from "../api/client";
import { fetchAllPages, getErrorMessage } from "../api/utils";
import { useClientFilter } from "../filters/ClientFilterContext";
import { TaskFormPanel } from "./TaskFormPanel";

const PRIORITY_ORDER = ["high", "medium", "low"];
const PRIORITY_LABELS = { high: "High priority", medium: "Medium priority", low: "Low priority" };

function getTaskPromptMessage(count) {
  return count === 0
    ? "Select one client before creating a task."
    : "Select exactly one client before creating a task.";
}

function formatDeadline(deadline) {
  const date = new Date(deadline);
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function isOverdue(task) {
  return !task.completed_at && new Date(task.deadline) < new Date();
}

export function TaskPanel({ className, onStateChange }) {
  const { selectedClientIds, supportsClientFiltering } = useClientFilter();
  const [tasks, setTasks] = useState([]);
  const [isLoadingTasks, setIsLoadingTasks] = useState(true);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [editingTask, setEditingTask] = useState(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [createPromptMessage, setCreatePromptMessage] = useState("");
  const [dragId, setDragId] = useState(null);
  const [dragOverKey, setDragOverKey] = useState(null);

  const canCreateForSelection = !supportsClientFiltering || selectedClientIds.length === 1;

  async function loadTasks() {
    if (supportsClientFiltering && selectedClientIds.length === 0) {
      setTasks([]);
      setIsLoadingTasks(false);
      return;
    }
    setIsLoadingTasks(true);
    setErrorMessage("");
    try {
      const params = {};
      if (supportsClientFiltering) params.client_ids = selectedClientIds.join(",");
      const all = await fetchAllPages("/tasks/", { params });
      setTasks(all);
    } catch (error) {
      setTasks([]);
      setErrorMessage(getErrorMessage(error, "We couldn't load tasks right now."));
    } finally {
      setIsLoadingTasks(false);
    }
  }

  const selectedKey = selectedClientIds.join(",");
  useEffect(() => {
    loadTasks();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedKey, supportsClientFiltering]);

  useEffect(() => {
    if (canCreateForSelection) setCreatePromptMessage("");
  }, [canCreateForSelection]);

  // Group + sort: active tasks by priority bucket then sort_order; completed last.
  const grouped = useMemo(() => {
    const active = tasks.filter((t) => !t.completed_at);
    const completed = tasks.filter((t) => t.completed_at);
    const byPriority = { high: [], medium: [], low: [] };
    for (const t of active) {
      (byPriority[t.priority] || byPriority.medium).push(t);
    }
    for (const key of PRIORITY_ORDER) {
      byPriority[key].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
    }
    return { byPriority, completed };
  }, [tasks]);

  const totalTaskCount = tasks.length;

  useEffect(() => {
    onStateChange?.({
      isEmpty: totalTaskCount === 0,
      isExpanded: !isCollapsed,
      isMinimized: isCollapsed,
      totalTaskCount,
    });
  }, [isCollapsed, onStateChange, totalTaskCount]);

  function closeForms() {
    setIsCreating(false);
    setEditingTask(null);
  }

  async function handleSaved() {
    closeForms();
    await loadTasks();
  }

  async function toggleComplete(task, e) {
    e.stopPropagation();
    try {
      await apiClient.patch(`/tasks/${task.id}/`, {
        completed_at: task.completed_at ? null : new Date().toISOString(),
      });
      await loadTasks();
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Couldn't update the task."));
    }
  }

  // ---- Drag and drop ----
  function handleDragStart(taskId) {
    setDragId(taskId);
  }

  function handleDragOver(e, priority, index) {
    e.preventDefault();
    setDragOverKey(`${priority}:${index}`);
  }

  async function handleDrop(e, targetPriority, targetIndex) {
    e.preventDefault();
    const draggedId = dragId;
    setDragId(null);
    setDragOverKey(null);
    if (!draggedId) return;

    const dragged = tasks.find((t) => t.id === draggedId);
    if (!dragged) return;

    // Build the new ordering for the target bucket.
    const bucket = grouped.byPriority[targetPriority].filter((t) => t.id !== draggedId);
    bucket.splice(targetIndex, 0, { ...dragged, priority: targetPriority });

    // Optimistic local update.
    const reindexed = bucket.map((t, i) => ({ ...t, priority: targetPriority, sort_order: i }));
    setTasks((current) => {
      const others = current.filter(
        (t) => t.id === draggedId || !grouped.byPriority[targetPriority].some((b) => b.id === t.id),
      );
      const untouched = current.filter(
        (t) => t.id !== draggedId && !reindexed.some((r) => r.id === t.id),
      );
      return [...untouched, ...reindexed];
    });

    // Persist.
    try {
      await apiClient.post("/tasks/reorder/", {
        items: reindexed.map((t) => ({ id: t.id, priority: targetPriority, sort_order: t.sort_order })),
      });
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Couldn't save the new order."));
      await loadTasks();
    }
  }

  function startCreate() {
    if (!canCreateForSelection) {
      setCreatePromptMessage(getTaskPromptMessage(selectedClientIds.length));
      return;
    }
    setCreatePromptMessage("");
    setEditingTask(null);
    setIsCreating(true);
  }

  if (isCollapsed) {
    return (
      <div className={`${className} task-panel-collapsed`}>
        <button
          aria-label="Expand tasks"
          className="task-panel-expand-tab"
          onClick={() => setIsCollapsed(false)}
          type="button"
        >
          <span className="task-panel-expand-icon">‹</span>
          <span className="task-panel-expand-label">Tasks{totalTaskCount > 0 ? ` (${totalTaskCount})` : ""}</span>
        </button>
      </div>
    );
  }

  return (
    <article className={className}>
      <div className="task-panel-header">
        <h3 className="task-panel-title">Tasks</h3>
        <div className="task-panel-header-actions">
          <button className="task-create-button" onClick={isCreating ? closeForms : startCreate} type="button">
            {isCreating ? "Cancel" : "+ Task"}
          </button>
          <button
            aria-label="Hide tasks panel"
            title="Hide tasks panel"
            className="task-panel-collapse-btn"
            onClick={() => setIsCollapsed(true)}
            type="button"
          >
            <span className="task-panel-collapse-label">Hide</span>
            <span aria-hidden="true">›</span>
          </button>
        </div>
      </div>

      {createPromptMessage ? <p className="task-create-error">{createPromptMessage}</p> : null}
      {errorMessage ? <p className="form-error">{errorMessage}</p> : null}
      {isLoadingTasks ? <p className="subtle-copy">Loading tasks…</p> : null}

      {isCreating || editingTask ? (
        <TaskFormPanel onCancel={closeForms} onSaved={handleSaved} task={editingTask} />
      ) : null}

      {!isLoadingTasks && totalTaskCount === 0 && !isCreating ? (
        <div className="task-empty-state">
          <h4>No tasks yet</h4>
          <p className="subtle-copy">Add a task and set its priority. Drag to reorder anytime.</p>
          <button className="task-create-button" onClick={startCreate} type="button">
            Create your first task
          </button>
        </div>
      ) : null}

      {!isLoadingTasks && totalTaskCount > 0 ? (
        <div className="task-priority-groups">
          {PRIORITY_ORDER.map((priority) => {
            const bucket = grouped.byPriority[priority];
            return (
              <section key={priority} className={`task-priority-group task-priority-${priority}`}>
                <header className="task-priority-header">
                  <span className={`task-priority-dot task-priority-dot-${priority}`} />
                  <span className="task-priority-label">{PRIORITY_LABELS[priority]}</span>
                  <span className="task-priority-count">{bucket.length}</span>
                </header>
                <div
                  className="task-priority-dropzone"
                  onDragOver={(e) => handleDragOver(e, priority, bucket.length)}
                  onDrop={(e) => handleDrop(e, priority, bucket.length)}
                >
                  {bucket.length === 0 ? (
                    <p className="task-priority-empty">Drop tasks here</p>
                  ) : (
                    bucket.map((task, index) => (
                      <article
                        key={task.id}
                        className={`task-card${dragId === task.id ? " dragging" : ""}${
                          dragOverKey === `${priority}:${index}` ? " drag-over" : ""
                        }${isOverdue(task) ? " overdue" : ""}`}
                        draggable
                        onDragStart={() => handleDragStart(task.id)}
                        onDragEnd={() => { setDragId(null); setDragOverKey(null); }}
                        onDragOver={(e) => handleDragOver(e, priority, index)}
                        onDrop={(e) => handleDrop(e, priority, index)}
                        onClick={() => { setEditingTask(task); setIsCreating(false); }}
                      >
                        <span className="task-card-grip" aria-hidden>⠿</span>
                        <button
                          className={`task-card-check${task.completed_at ? " checked" : ""}`}
                          onClick={(e) => toggleComplete(task, e)}
                          aria-label={task.completed_at ? "Mark incomplete" : "Mark complete"}
                          type="button"
                        >
                          {task.completed_at ? "✓" : ""}
                        </button>
                        <div className="task-card-body">
                          <span className="task-card-title">{task.title}</span>
                          <span className={`task-card-deadline${isOverdue(task) ? " overdue" : ""}`}>
                            {isOverdue(task) ? "Overdue · " : ""}{formatDeadline(task.deadline)}
                          </span>
                        </div>
                      </article>
                    ))
                  )}
                </div>
              </section>
            );
          })}

          {grouped.completed.length > 0 ? (
            <section className="task-priority-group task-completed-group">
              <header className="task-priority-header">
                <span className="task-priority-label">Completed</span>
                <span className="task-priority-count">{grouped.completed.length}</span>
              </header>
              <div className="task-priority-dropzone">
                {grouped.completed.map((task) => (
                  <article
                    key={task.id}
                    className="task-card completed"
                    onClick={() => { setEditingTask(task); setIsCreating(false); }}
                  >
                    <span className="task-card-grip" aria-hidden />
                    <button
                      className="task-card-check checked"
                      onClick={(e) => toggleComplete(task, e)}
                      aria-label="Mark incomplete"
                      type="button"
                    >
                      ✓
                    </button>
                    <div className="task-card-body">
                      <span className="task-card-title">{task.title}</span>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
