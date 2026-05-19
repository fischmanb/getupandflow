import { Outlet } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { CALENDAR_VIEWS } from "../calendar/calendarUtils";
import { CalendarControlsProvider, useCalendarControls } from "../calendar/CalendarControlsContext";
import { HamburgerMenu } from "./HamburgerMenu";
import { ClientFilterProvider, useClientFilter } from "../filters/ClientFilterContext";

function getDisplayName(user) {
  if (!user) return "";
  return [user.first_name, user.last_name].filter(Boolean).join(" ") || user.username;
}

function ActiveClientGreeting() {
  const { user } = useAuth();
  const { selectedClients, supportsClientFiltering } = useClientFilter();

  if (!supportsClientFiltering) {
    return <p className="shell-greeting">Welcome, {getDisplayName(user)}</p>;
  }

  if (selectedClients.length === 1) {
    return <p className="shell-greeting">Welcome, {selectedClients[0].label}</p>;
  }
  if (selectedClients.length === 0) {
    return <p className="shell-greeting">No client selected</p>;
  }
  return <p className="shell-greeting">Viewing {selectedClients.length} clients</p>;
}

function ShellHeader() {
  const { goToToday, view, setView } = useCalendarControls();

  return (
    <header className="shell-header">
      <div className="shell-branding">
        <p className="eyebrow">Get Up and Flow</p>
        <ActiveClientGreeting />
      </div>
      <div className="shell-header-actions">
        <div className="shell-calendar-controls">
          <button className="calendar-today-button" onClick={goToToday} type="button">
            Today
          </button>
          <label className="shell-view-select">
            <span className="visually-hidden">Calendar view</span>
            <select value={view} onChange={(event) => setView(event.target.value)}>
              {CALENDAR_VIEWS.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <HamburgerMenu />
      </div>
    </header>
  );
}

export function AppShell() {
  return (
    <ClientFilterProvider>
      <CalendarControlsProvider>
        <div className="shell-root">
          <ShellHeader />
          <Outlet />
        </div>
      </CalendarControlsProvider>
    </ClientFilterProvider>
  );
}
