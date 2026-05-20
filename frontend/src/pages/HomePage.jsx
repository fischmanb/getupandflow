import { useState } from "react";

import { BigCalendarPanel } from "../components/BigCalendarPanel";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { TaskPanel } from "../components/TaskPanel";

function CalendarIcon() {
  return (
    <svg aria-hidden="true" className="toggle-button-icon" viewBox="0 0 24 24">
      <rect x="3.5" y="5.5" width="17" height="15" rx="2.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="M7 3.75v3.5M17 3.75v3.5M3.5 9.5h17" fill="none" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

function TaskIcon() {
  return (
    <svg aria-hidden="true" className="toggle-button-icon" viewBox="0 0 24 24">
      <path d="M9 7h10M9 12h10M9 17h10M4.5 7.5l1.75 1.75L8.75 6.5M4.5 12.5l1.75 1.75L8.75 11.5M4.5 17.5l1.75 1.75L8.75 16.5" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
    </svg>
  );
}

export function HomePage() {
  const [activeMobileView, setActiveMobileView] = useState("calendar");
  const [taskPanelState, setTaskPanelState] = useState({
    isEmpty: false,
    isExpanded: false,
    isMinimized: false,
    totalTaskCount: 0,
  });

  const shouldPrioritizeCalendar = taskPanelState.isEmpty && taskPanelState.isMinimized;

  return (
    <main className="workspace-shell">
      <section className="mobile-toggle-bar" aria-label="Mobile view toggle">
        <button
          className={activeMobileView === "calendar" ? "toggle-button active" : "toggle-button"}
          onClick={() => setActiveMobileView("calendar")}
          type="button"
        >
          <CalendarIcon />
          <span>Calendar</span>
        </button>
        <button
          className={activeMobileView === "tasks" ? "toggle-button active" : "toggle-button"}
          onClick={() => setActiveMobileView("tasks")}
          type="button"
        >
          <TaskIcon />
          <span>Tasks</span>
        </button>
      </section>

      <section className={shouldPrioritizeCalendar ? "workspace-grid workspace-grid-prioritize-calendar" : "workspace-grid"}>
        <ErrorBoundary>
          <BigCalendarPanel
            className={
              activeMobileView === "calendar"
                ? "workspace-panel calendar-panel"
                : "workspace-panel calendar-panel mobile-hidden"
            }
          />
        </ErrorBoundary>
        <ErrorBoundary>
          <TaskPanel
            onStateChange={setTaskPanelState}
            className={activeMobileView === "tasks" ? "workspace-panel tasks-panel" : "workspace-panel tasks-panel mobile-hidden"}
          />
        </ErrorBoundary>
      </section>
    </main>
  );
}
