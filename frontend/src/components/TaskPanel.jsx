import { useEffect, useRef, useState } from "react";

import { apiClient } from "../api/client";
import { getErrorMessage, getListData, getPaginationMeta } from "../api/utils";
import { useClientFilter } from "../filters/ClientFilterContext";
import { PaginationControls } from "./PaginationControls";
import { TaskFormPanel } from "./TaskFormPanel";

function getTaskPromptMessage(selectedClientCount) {
  if (selectedClientCount === 0) {
    return "Select one client before creating a task.";
  }

  return "Select exactly one client before creating a task.";
}

function formatDeadline(deadline) {
  const date = new Date(deadline);
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function TaskPanel({ className, onStateChange }) {
  const { selectedClientIds, supportsClientFiltering } = useClientFilter();
  const [tasks, setTasks] = useState([]);
  const [isLoadingTasks, setIsLoadingTasks] = useState(true);
  const [isMobileViewport, setIsMobileViewport] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia("(max-width: 768px)").matches : false,
  );
  const [isExpanded, setIsExpanded] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [editingTask, setEditingTask] = useState(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [totalTaskCount, setTotalTaskCount] = useState(0);
  const [createPromptMessage, setCreatePromptMessage] = useState("");
  const previousTaskCountRef = useRef(0);

  async function loadTasks(page = currentPage) {
    if (supportsClientFiltering && selectedClientIds.length === 0) {
      setTasks([]);
      setTotalPages(0);
      setTotalTaskCount(0);
      setCurrentPage(1);
      setIsLoadingTasks(false);
      return;
    }

    setIsLoadingTasks(true);
    setErrorMessage("");
    try {
      const params = { page };
      if (supportsClientFiltering) {
        params.client_ids = selectedClientIds.join(",");
      }
      const response = await apiClient.get("/tasks/", { params });
      const nextTasks = getListData(response.data);
      const meta = getPaginationMeta(response.data);
      setTasks(nextTasks);
      setTotalPages(meta.totalPages);
      setTotalTaskCount(meta.count);
      setCurrentPage(page);
      setIsExpanded((current) => (meta.count > 0 ? true : current));
    } catch (error) {
      setTasks([]);
      setTotalPages(0);
      setTotalTaskCount(0);
      setErrorMessage(getErrorMessage(error, "We couldn't load tasks right now."));
    } finally {
      setIsLoadingTasks(false);
    }
  }

  const selectedClientIdsKey = selectedClientIds.join(",");

  useEffect(() => {
    loadTasks(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedClientIdsKey, supportsClientFiltering]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }

    const mediaQuery = window.matchMedia("(max-width: 768px)");
    const handleChange = (event) => setIsMobileViewport(event.matches);

    setIsMobileViewport(mediaQuery.matches);

    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", handleChange);
      return () => mediaQuery.removeEventListener("change", handleChange);
    }

    mediaQuery.addListener(handleChange);
    return () => mediaQuery.removeListener(handleChange);
  }, []);

  useEffect(() => {
    if (previousTaskCountRef.current === 0 && totalTaskCount > 0) {
      setIsExpanded(true);
    }
    previousTaskCountRef.current = totalTaskCount;
  }, [totalTaskCount]);

  const isEmpty = totalTaskCount === 0;
  const shouldShowMinimized = !isLoadingTasks && isEmpty && !isExpanded && !isMobileViewport;
  const canCreateForSelection = !supportsClientFiltering || selectedClientIds.length === 1;

  useEffect(() => {
    if (canCreateForSelection) {
      setCreatePromptMessage("");
    }
  }, [canCreateForSelection]);

  useEffect(() => {
    onStateChange?.({
      isEmpty,
      isExpanded,
      isMinimized: shouldShowMinimized,
      totalTaskCount,
    });
  }, [isEmpty, isExpanded, onStateChange, shouldShowMinimized, totalTaskCount]);

  function closeForms() {
    setIsCreating(false);
    setEditingTask(null);
  }

  async function handleSaved() {
    closeForms();
    await loadTasks(1);
    setIsExpanded(true);
  }

  if (shouldShowMinimized) {
    return (
      <div className="task-panel-launcher-shell">
        <button
          aria-label="Open task panel"
          className="task-panel-launcher"
          onClick={() => setIsExpanded(true)}
          type="button"
        >
          <svg
            aria-hidden="true"
            className="task-panel-launcher-icon"
            fill="none"
            viewBox="0 0 24 24"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              d="M9 7h10M9 12h10M9 17h10M4.5 7.5l1.75 1.75L8.75 6.5M4.5 12.5l1.75 1.75L8.75 11.5M4.5 17.5l1.75 1.75L8.75 16.5"
              stroke="currentColor"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="1.8"
            />
          </svg>
        </button>
      </div>
    );
  }

  return (
    <article className={className}>
      <div className="task-panel-header">
        <h4 className="task-panel-title">Tasks</h4>
        <div className="task-panel-actions">
          <div className="task-panel-action-row">
            {!isLoadingTasks && !shouldShowMinimized ? (
              <button
                className="task-create-button"
                onClick={() => {
                  if (isCreating || createPromptMessage) {
                    setCreatePromptMessage("");
                    closeForms();
                    return;
                  }
                  if (!canCreateForSelection) {
                    setCreatePromptMessage(getTaskPromptMessage(selectedClientIds.length));
                    return;
                  }
                  setCreatePromptMessage("");
                  setIsCreating(true);
                  setEditingTask(null);
                }}
                type="button"
              >
                {isCreating || createPromptMessage ? "X" : "+ Task"}
              </button>
            ) : null}
            {!isLoadingTasks ? (
              !isMobileViewport ? (
                <button
                  className="task-panel-toggle"
                  onClick={() => setIsExpanded((current) => !current)}
                  type="button"
                >
                  {shouldShowMinimized ? "+" : "-"}
                </button>
              ) : null
            ) : null}
          </div>
          {createPromptMessage ? <p className="task-create-error">{createPromptMessage}</p> : null}
        </div>
      </div>

      {isLoadingTasks ? <p className="subtle-copy">Loading tasks...</p> : null}
      {errorMessage ? <p className="form-error">{errorMessage}</p> : null}

      {!isLoadingTasks && !shouldShowMinimized && isEmpty ? (
        <div className="task-empty-state">
          <h4>Create your first task</h4>
          <p className="subtle-copy">
            The panel starts minimized when empty. Create a real task here to trigger the first-task auto-expand
            behavior.
          </p>
          <button
            className="task-create-button"
            onClick={() => {
              if (!canCreateForSelection) {
                setCreatePromptMessage(getTaskPromptMessage(selectedClientIds.length));
                return;
              }
              setCreatePromptMessage("");
              setIsCreating(true);
            }}
            type="button"
          >
            Create your first task
          </button>
        </div>
      ) : null}

      {isCreating || editingTask ? (
        <TaskFormPanel onCancel={closeForms} onSaved={handleSaved} task={editingTask} />
      ) : null}

      {!isLoadingTasks && tasks.length > 0 ? (
        <>
          <div className="task-list">
            {tasks.map((task) => (
              <article
                key={task.id}
                className="task-list-item task-list-item-interactive"
                onClick={() => {
                  setEditingTask(task);
                  setIsCreating(false);
                }}
              >
                <div className="task-list-topline">
                  <h4>{task.title}</h4>
                  <span>{formatDeadline(task.deadline)}</span>
                </div>
                <p>{task.description || "No description provided."}</p>
                <small>Click to edit</small>
              </article>
            ))}
          </div>
          <PaginationControls
            currentPage={currentPage}
            isLoading={isLoadingTasks}
            label="tasks"
            onPageChange={loadTasks}
            totalPages={totalPages}
          />
        </>
      ) : null}
    </article>
  );
}
