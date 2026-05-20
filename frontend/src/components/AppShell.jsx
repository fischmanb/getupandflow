import { Outlet } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { CalendarControlsProvider } from "../calendar/CalendarControlsContext";
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
  return (
    <header className="shell-header">
      <div className="shell-branding">
        <p className="eyebrow">Get Up and Flow</p>
        <ActiveClientGreeting />
      </div>
      <div className="shell-header-actions">
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
